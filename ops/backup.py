"""
Encrypted backup of the installed Save-Pass database (task 36). Run daily by
the task "\\Save-Pass\\Backup"; safe to run by hand.

    python ops/backup.py [--env FILE] [--out DIR] [--pg-bin DIR]
                         [--keep-daily 14] [--keep-monthly 12]

pg_dump (custom format) with the read-only backup role (BACKUP_DATABASE_URL),
encrypted with AES-256-GCM (BACKUP_KEY); the plain dump never stays on disk.
Keeps the newest daily backups plus the newest of each recent month.

The dump holds bcrypt hashes and Fernet-encrypted credentials: keep
FERNET_KEY (and BACKUP_KEY) in your password manager, apart from the backups.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oplib import (  # noqa: E402
    DEFAULTS,
    assert_not_on_c,
    backup_key,
    backups_to_keep,
    encrypt_file,
    logger,
    pg,
    read_env,
    stamp,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=DEFAULTS["env_file"])
    parser.add_argument("--out", default=DEFAULTS["backup_dir"])
    parser.add_argument("--pg-bin", default=DEFAULTS["pg_bin"])
    parser.add_argument("--keep-daily", type=int, default=14)
    parser.add_argument("--keep-monthly", type=int, default=12)
    args = parser.parse_args(argv)

    out = Path(args.out)
    assert_not_on_c(out, "The backup folder")
    out.mkdir(parents=True, exist_ok=True)
    log = logger(out / "backup.log")
    try:
        settings = read_env(args.env)
        uri = settings.get("BACKUP_DATABASE_URL")
        if not uri:
            raise ValueError("BACKUP_DATABASE_URL is missing.")
        key = backup_key(settings)
        name = f"savepass-{stamp()}.dump.enc"
        plain = out / f"{name}.partial"
        final = out / name
        try:
            pg(args.pg_bin, "pg_dump", [
                "--format=custom", "--no-owner", "--no-privileges",
                f"--file={plain}", f"--dbname={uri}",
            ])
            encrypt_file(plain, final, key)
        finally:
            plain.unlink(missing_ok=True)
        log(f"OK {final} ({final.stat().st_size // 1024} KB)")

        names = [p.name for p in out.iterdir()]
        keep = backups_to_keep(names, args.keep_daily, args.keep_monthly)
        for old in names:
            if old.startswith("savepass-") and old.endswith(".dump.enc") and old not in keep:
                (out / old).unlink()
                log(f"Removed {old}")
        return 0
    except Exception as exc:  # noqa: BLE001 — logged for the scheduled task
        log(f"FAILED {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
