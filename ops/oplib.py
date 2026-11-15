"""
Shared helpers of the Save-Pass operation jobs (local installation, task 36).

They run with the installation's own Python (``Y:\\Apps\\Save-Pass\\python``),
which has ``cryptography`` from the backend requirements.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULTS = {
    "env_file": r"Y:\Apps\Save-Pass\.env.production",
    "backup_dir": r"Y:\Code\Git\Repos\Save - Pass\Backup\db",
    "pg_bin": r"C:\Program Files\PostgreSQL\18\bin",
}

# AES-256-GCM file format: "SPB1" | nonce (12) | ciphertext with its 16-byte tag.
MAGIC = b"SPB1"
BACKUP_NAME = re.compile(r"^savepass-(\d{8})-(\d{4})\.dump\.enc$")


def read_env(path: str | os.PathLike) -> dict[str, str]:
    """KEY=value lines (no shell expansion; surrounding quotes removed)."""
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
        if match:
            value = match.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[match.group(1)] = value
    return values


def backup_key(settings: dict[str, str]) -> bytes:
    try:
        key = base64.b64decode(settings.get("BACKUP_KEY", ""), validate=True)
    except ValueError:
        key = b""
    if len(key) != 32:
        raise ValueError("BACKUP_KEY must be 32 bytes in base64.")
    return key


def encrypt_file(src: Path, dest: Path, key: bytes) -> None:
    nonce = os.urandom(12)
    body = AESGCM(key).encrypt(nonce, src.read_bytes(), MAGIC)
    dest.write_bytes(MAGIC + nonce + body)


def decrypt_file(src: Path, dest: Path, key: bytes) -> None:
    data = src.read_bytes()
    if len(data) < 32 or data[:4] != MAGIC:
        raise ValueError(f"Not a Save-Pass backup: {src}")
    dest.write_bytes(AESGCM(key).decrypt(data[4:16], data[16:], MAGIC))


def stamp(now: datetime | None = None) -> str:
    # Local time on purpose: file names match the clock of whoever reads them.
    return (now or datetime.now().astimezone()).strftime("%Y%m%d-%H%M")


def backups_to_keep(names: list[str], keep_daily: int, keep_monthly: int) -> set[str]:
    """Newest *keep_daily* backups plus the newest of each of the last
    *keep_monthly* months."""
    ordered = sorted((n for n in names if BACKUP_NAME.match(n)), reverse=True)
    keep = set(ordered[:keep_daily])
    months: list[str] = []
    for name in ordered:
        month = BACKUP_NAME.match(name).group(1)[:6]
        if month in months or len(months) >= keep_monthly:
            continue
        months.append(month)
        keep.add(name)
    return keep


def with_database(uri: str, database: str) -> str:
    parts = urlsplit(uri)
    return urlunsplit(parts._replace(path=f"/{database}"))


def pg(pg_bin: str, tool: str, args: list[str]) -> str:
    """Run a PostgreSQL client tool; raise with its output when it fails."""
    exe = Path(pg_bin) / (f"{tool}.exe" if os.name == "nt" else tool)
    result = subprocess.run([str(exe), *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{tool} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def logger(path: Path | None):
    def log(text: str) -> None:
        print(text, flush=True)
        if path:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"{datetime.now().astimezone().isoformat(timespec='seconds')} {text}\n")

    return log


def assert_not_on_c(path: str | os.PathLike, what: str) -> None:
    if re.match(r"^[cC]:", str(Path(path).resolve())):
        raise SystemExit(f"{what} must not be on C: ({path}).")
