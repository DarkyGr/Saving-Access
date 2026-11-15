"""
Local installation helpers (task 36): encrypted backups, rotation, settings
template, web.config and the web folder sync of the release script.
"""

import base64
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ops"))

import oplib  # noqa: E402


def _load_release():
    spec = importlib.util.spec_from_file_location("release", REPO / "scripts" / "release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _load_release()
KEY = os.urandom(32)


# ── Backups ──────────────────────────────────────────────────────────────────


def test_encrypt_roundtrip(tmp_path):
    plain, enc, back = tmp_path / "d", tmp_path / "d.enc", tmp_path / "d.out"
    plain.write_bytes(b"PGDMP" + os.urandom(2048))
    oplib.encrypt_file(plain, enc, KEY)
    data = enc.read_bytes()
    assert data[:4] == b"SPB1" and plain.read_bytes() not in data
    oplib.decrypt_file(enc, back, KEY)
    assert back.read_bytes() == plain.read_bytes()


def test_decrypt_rejects_wrong_key_tampering_and_other_files(tmp_path):
    from cryptography.exceptions import InvalidTag

    plain, enc = tmp_path / "d", tmp_path / "d.enc"
    plain.write_bytes(b"secret dump")
    oplib.encrypt_file(plain, enc, KEY)
    with pytest.raises(InvalidTag):
        oplib.decrypt_file(enc, tmp_path / "x", os.urandom(32))
    tampered = bytearray(enc.read_bytes())
    tampered[-1] ^= 1
    enc.write_bytes(bytes(tampered))
    with pytest.raises(InvalidTag):
        oplib.decrypt_file(enc, tmp_path / "x", KEY)
    plain.write_bytes(b"not a backup at all, just some bytes")
    with pytest.raises(ValueError, match="Not a Save-Pass backup"):
        oplib.decrypt_file(plain, tmp_path / "x", KEY)


def test_backup_key_must_be_32_bytes():
    assert oplib.backup_key({"BACKUP_KEY": base64.b64encode(KEY).decode()}) == KEY
    for bad in ("", "abc", base64.b64encode(os.urandom(16)).decode(), "!!!"):
        with pytest.raises(ValueError, match="32 bytes"):
            oplib.backup_key({"BACKUP_KEY": bad})


def test_rotation_keeps_daily_and_monthly():
    names = [f"savepass-2026{m:02d}{d:02d}-0230.dump.enc" for m in range(1, 12) for d in (1, 15, 28)]
    names += ["backup.log", "savepass-20261101-0230.dump.enc.partial"]
    keep = oplib.backups_to_keep(names, keep_daily=4, keep_monthly=6)
    newest = sorted(n for n in names if n.endswith(".enc"))[-4:]
    assert set(newest) <= keep
    months = {n[9:15] for n in keep}
    assert len(months) == 6 and "202611" in months and "202606" in months
    assert "savepass-20260101-0230.dump.enc" not in keep
    assert all(n.endswith(".dump.enc") for n in keep)


def test_stamp_and_with_database():
    assert oplib.stamp(datetime(2026, 11, 14, 2, 30)) == "20261114-0230"
    uri = "postgresql://savepass_backup:p%40ss@127.0.0.1:5435/savepass"
    assert oplib.with_database(uri, "scratch") == "postgresql://savepass_backup:p%40ss@127.0.0.1:5435/scratch"


def test_read_env(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# c\nA=1\nB = "two words" \nC=\'x=y\'\nbad line\nD=\n', encoding="utf-8")
    assert oplib.read_env(f) == {"A": "1", "B": "two words", "C": "x=y", "D": ""}


# ── Release script ───────────────────────────────────────────────────────────


def test_example_settings_are_complete_and_valid(tmp_path, monkeypatch):
    f = tmp_path / ".env.production"
    f.write_text(release.example_settings(), encoding="utf-8")
    settings = oplib.read_env(f)
    release.check_settings(settings, f)
    assert settings["APP_BASE_URL"].endswith(".local:8443")
    assert settings["DATABASE_URL"].startswith("postgresql://savepass_app:")
    assert ":5435/savepass" in settings["BACKUP_DATABASE_URL"]
    assert len(oplib.backup_key(settings)) == 32
    # The backend accepts the generated secrets.
    from app import security

    monkeypatch.setenv("JWT_SECRET", settings["JWT_SECRET"])
    monkeypatch.setenv("FERNET_KEY", settings["FERNET_KEY"])
    security.validate_settings()
    # Two runs never share secrets.
    assert release.example_settings() != release.example_settings()


def test_check_settings_rejects_missing_values(tmp_path):
    f = tmp_path / ".env.production"
    f.write_text(release.example_settings().replace("JWT_SECRET=", "JWT_SECRET=CHANGE_ME"), encoding="utf-8")
    with pytest.raises(SystemExit, match="JWT_SECRET"):
        release.check_settings(oplib.read_env(f), f)
    settings = oplib.read_env(f) | {"JWT_SECRET": "x" * 40, "API_PORT": "eighty"}
    with pytest.raises(SystemExit, match="API_PORT"):
        release.check_settings(settings, f)


def test_release_refuses_c_drive():
    if os.name != "nt":
        pytest.skip("Windows paths")
    with pytest.raises(SystemExit, match="C:"):
        release.main(["--to", r"C:\Apps\Save-Pass"])


def test_first_release_writes_template_and_stops(tmp_path):
    target = tmp_path / "Save-Pass"
    if os.name == "nt" and str(target).lower().startswith("c:"):
        pytest.skip("temp folder on C:")
    assert release.main(["--to", str(target)]) == 0
    assert (target / ".env.production.example").exists()
    assert not (target / "app").exists()


def test_sync_web_mirrors_and_writes_web_config(tmp_path):
    dist, web = tmp_path / "dist", tmp_path / "web"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "app-NEW.js").write_text("new")
    (web / "assets").mkdir(parents=True)
    (web / "assets" / "app-OLD.js").write_text("old")
    (web / "stale-folder").mkdir()
    (web / "stale-folder" / "x.txt").write_text("x")

    release.sync_web(dist, web, "8010")

    assert sorted(p.relative_to(web).as_posix() for p in web.rglob("*")) == [
        "assets", "assets/app-NEW.js", "index.html", "web.config",
    ]
    config = (web / "web.config").read_text(encoding="utf-8")
    assert "http://127.0.0.1:8010/api/{R:1}" in config and "{{API_PORT}}" not in config
    assert "HTTP_X_CLIENT_IP" in config and "Content-Security-Policy" in config


def test_web_config_is_valid_xml():
    import xml.etree.ElementTree as ET

    text = (REPO / "deploy" / "iis" / "web.config.template").read_text(encoding="utf-8")
    root = ET.fromstring(text.replace("{{API_PORT}}", "8010"))
    rules = root.findall("./system.webServer/rewrite/rules/rule")
    assert [r.get("name") for r in rules] == ["Save-Pass API", "Save-Pass SPA"]
    headers = {h.get("name") for h in root.findall("./system.webServer/httpProtocol/customHeaders/add")}
    assert {"Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options"} <= headers
