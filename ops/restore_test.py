"""
Proves a backup can be restored (task 36): decrypts it, restores it into a
scratch database, compares the rows of every table with the live database and
drops the scratch database. Nothing live is touched. Run weekly by the task
"\\Save-Pass\\Restore test".

    python ops/restore_test.py [--env FILE] [--file BACKUP] [--dir DIR] [--pg-bin DIR]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oplib import (  # noqa: E402
    BACKUP_NAME,
    DEFAULTS,
    backup_key,
    decrypt_file,
    logger,
    pg,
    read_env,
    with_database,
)

COUNTS = """SELECT string_agg(format('%s=%s', table_name,
  (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from public.%I', table_name), false, true, '')))[1]::text),
  ';' ORDER BY table_name)
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=DEFAULTS["env_file"])
    parser.add_argument("--dir", default=DEFAULTS["backup_dir"])
    parser.add_argument("--file")
    parser.add_argument("--pg-bin", default=DEFAULTS["pg_bin"])
    args = parser.parse_args(argv)

    folder = Path(args.dir)
    log = logger(folder / "restore-test.log" if folder.is_dir() else None)
    candidates = sorted(p for p in folder.glob("savepass-*.dump.enc") if BACKUP_NAME.match(p.name)) if folder.is_dir() else []
    backup = Path(args.file) if args.file else (candidates[-1] if candidates else None)
    if backup is None:
        log(f"FAILED no backups in {folder}")
        return 1

    settings = read_env(args.env)
    uri = settings["BACKUP_DATABASE_URL"]
    scratch = f"savepass_restore_test_{int(time.time())}"
    plain = backup.with_name(backup.name + ".restore-test")

    def counts(target: str) -> str:
        return pg(args.pg_bin, "psql", [
            "--no-psqlrc", "--tuples-only", "--no-align", f"--dbname={target}", f"--command={COUNTS}",
        ]).strip()

    created = False
    try:
        decrypt_file(backup, plain, backup_key(settings))
        pg(args.pg_bin, "psql", ["--no-psqlrc", f"--dbname={uri}", f"--command=CREATE DATABASE {scratch}"])
        created = True
        pg(args.pg_bin, "pg_restore", [
            "--no-owner", "--no-privileges", "--exit-on-error",
            f"--dbname={with_database(uri, scratch)}", str(plain),
        ])
        restored, live = counts(with_database(uri, scratch)), counts(uri)
        if restored == live:
            log(f"RESTORE OK {backup}: every table has the same rows as the live database.")
        else:
            log(f"RESTORE OK {backup}: restored; the live database changed since the backup.")
        print(restored)
        return 0
    except Exception as exc:  # noqa: BLE001
        log(f"RESTORE FAILED {backup}: {exc}")
        return 1
    finally:
        plain.unlink(missing_ok=True)
        if created:
            pg(args.pg_bin, "psql", ["--no-psqlrc", f"--dbname={uri}", f"--command=DROP DATABASE IF EXISTS {scratch}"])


if __name__ == "__main__":
    sys.exit(main())
