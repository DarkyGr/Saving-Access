"""
Monitoring and alerts (task 35.3, Requirement 20): the checks, the alert
rules, log retention and the CLI command.
"""

import io
import json
import os
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services import monitor
from app.services.monitor import Problem


class _Ctx:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, *exc):
        return False


def _opener(body: dict | None = None, error: Exception | None = None):
    def opener(url, timeout, context):
        if error:
            raise error
        return _Ctx(io.BytesIO(json.dumps(body).encode()))

    return opener


def test_health_ok_and_failures():
    assert monitor.check_health("http://x/api/health", "api", opener=_opener({"status": "ok"})) == []
    bad = monitor.check_health("http://x/api/health", "api", opener=_opener({"status": "degraded"}))
    assert bad[0].key == "api" and "degraded" in bad[0].en
    down = monitor.check_health("http://x/api/health", "web", opener=_opener(error=ConnectionRefusedError()))
    assert down[0].key == "web" and "ConnectionRefusedError" in down[0].es


def _backup(folder, hours_old: float, name="savepass-20261116-0230.dump.enc"):
    path = folder / name
    path.write_bytes(b"x")
    stamp = time.time() - hours_old * 3600
    os.utime(path, (stamp, stamp))
    return path


def test_backups(tmp_path):
    assert [p.key for p in monitor.check_backups(tmp_path)] == ["backup"]
    _backup(tmp_path, 30)
    assert "30 hours" in monitor.check_backups(tmp_path)[0].en
    _backup(tmp_path, 2, "savepass-20261117-0230.dump.enc")
    assert monitor.check_backups(tmp_path) == []

    (tmp_path / "backup.log").write_text("OK a\nFAILED pg_dump: connection refused\n", encoding="utf-8")
    assert [p.key for p in monitor.check_backups(tmp_path)] == ["backup-failed"]
    (tmp_path / "backup.log").write_text("FAILED old\nOK new\n", encoding="utf-8")
    assert monitor.check_backups(tmp_path) == []


def test_restore_test_result_and_age(tmp_path):
    _backup(tmp_path, 1)
    log = tmp_path / "restore-test.log"
    log.write_text("RESTORE OK a\nRESTORE FAILED b: boom\n", encoding="utf-8")
    assert [p.key for p in monitor.check_backups(tmp_path)] == ["restore"]
    log.write_text("RESTORE OK b\n", encoding="utf-8")
    assert monitor.check_backups(tmp_path) == []
    old = time.time() - 9 * 86400
    os.utime(log, (old, old))
    assert "8 days" in monitor.check_backups(tmp_path)[0].en


def test_tasks_and_their_parsing():
    problems = monitor.check_tasks({"Backup": 0, "Restore test": 0x41303, "Reminders": 1})
    assert [p.key for p in problems] == ["task:Reminders"] and "0x1" in problems[0].en
    out = "API\t0\nBackup\t2147942402\nReminders\tx\nMonitor\t0\n"
    runner = lambda *a, **k: SimpleNamespace(stdout=out)  # noqa: E731
    assert monitor.task_results(runner=runner) == {"Backup": 2147942402, "Reminders": None}


def test_disk(tmp_path):
    assert monitor.check_disk(tmp_path, usage=lambda p: SimpleNamespace(free=50 * 1024**3)) == []
    low = monitor.check_disk(tmp_path, usage=lambda p: SimpleNamespace(free=1024**3))
    assert low[0].key == "disk" and "1.0 GB" in low[0].en


def test_rotation_and_pruning(tmp_path):
    log = tmp_path / "jobs.log"
    log.write_bytes(b"a" * 50)
    assert monitor.rotate(log, max_bytes=100) is False
    for n in range(5):
        log.write_bytes(bytes([65 + n]) * 200)
        assert monitor.rotate(log, max_bytes=100, keep=3)
    assert not log.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["jobs.log.1", "jobs.log.2", "jobs.log.3"]
    assert (tmp_path / "jobs.log.1").read_bytes()[:1] == b"E"  # newest

    iis = tmp_path / "iis" / "W3SVC2"
    iis.mkdir(parents=True)
    old, new = iis / "u_ex260101.log", iis / "u_ex261115.log"
    old.write_text("x")
    new.write_text("y")
    stamp = time.time() - 40 * 86400
    os.utime(old, (stamp, stamp))
    assert monitor.prune(tmp_path / "iis") == 1
    assert new.exists() and not old.exists()


def test_alert_rules():
    now = datetime(2026, 11, 16, 12, tzinfo=UTC)
    disk = [Problem("disk", "d", "d")]
    action, state = monitor.decide(disk, {}, now)
    assert action == "alert"
    # Same problem an hour later: quiet; after 24 hours: reminded.
    assert monitor.decide(disk, state, now + timedelta(hours=1))[0] is None
    assert monitor.decide(disk, state, now + timedelta(hours=25))[0] == "alert"
    # A new problem alerts at once.
    both = disk + [Problem("api", "a", "a")]
    assert monitor.decide(both, state, now + timedelta(hours=2))[0] == "alert"
    # Everything fine again: one "resolved", then quiet.
    action, state = monitor.decide([], state, now + timedelta(hours=3))
    assert action == "resolved"
    assert monitor.decide([], state, now + timedelta(hours=4))[0] is None


def test_alert_email_language():
    admin = SimpleNamespace(preferred_language="es", display_name=None, username="boss", email="boss@example.com")
    email = monitor.alert_email(admin, [Problem("disk", "Low disk.", "Poco disco.")], "alert")
    assert email.to == "boss@example.com" and "alerta (1 problema)" in email.subject and "- Poco disco." in email.body
    admin.preferred_language = "en"
    assert monitor.alert_email(admin, [], "resolved").subject == "Save-Pass: back to normal"


def test_cli_emails_the_admins_once(tmp_path, capsys, monkeypatch):
    from argparse import Namespace
    from unittest.mock import patch

    from sqlalchemy.orm import sessionmaker

    monkeypatch.setenv("DATABASE_URL", os.environ.get("DATABASE_URL", "sqlite:///:memory:"))
    from app import cli
    from app.models import User
    from tests.conftest import make_test_engine

    Session = sessionmaker(bind=make_test_engine())
    with Session() as db:
        for name, role in (("boss", "Admin"), ("alice", "User")):
            db.add(User(username=name, email=f"{name}@example.com", password_hash="x", role=role,
                        email_verified=True, creation_date=datetime.now(UTC).date(),
                        creation_time=datetime.now(UTC).time().replace(microsecond=0)))
        db.commit()

    args = Namespace(state=str(tmp_path / "state.json"), backup_dir=None, api_url="http://api/health",
                     web_url=None, no_web=True, no_tasks=True, rotate=None, iis_logs=None)
    down = [Problem("api", "API down.", "API caída.")]
    with patch.object(cli, "SessionLocal", Session),          patch("app.services.monitor.check_health", return_value=down),          patch("app.services.email_sender.send_email", return_value=True) as send:
        cli.cmd_monitor(args)
        cli.cmd_monitor(args)  # same problem: no second email
    assert [c.args[0].to for c in send.call_args_list] == ["boss@example.com"]
    assert "1 problem(s): api" in capsys.readouterr().out

