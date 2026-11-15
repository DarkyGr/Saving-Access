"""
Runs a Python module of the installed backend with the production settings
(task 36). Used by the scheduled tasks and by ``ops\\windows\\with-production.ps1``.

    python ops/run.py --env Y:\\Apps\\Save-Pass\\.env.production --cwd Y:\\Apps\\Save-Pass\\app \\
        uvicorn app.main:app --host 127.0.0.1 --port 8010
    python ops/run.py --env ... --cwd ... app.cli send-verification-reminders

Variables already set in the environment win over the file, so a one-off
override (for example ``DATABASE_URL`` of the migrator role) is possible.
Temporary files go to <install>\\tmp, never to C:.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oplib import read_env  # noqa: E402


def main() -> None:
    argv = sys.argv[1:]
    env_file = cwd = None
    while argv and argv[0] in ("--env", "--cwd"):
        flag, value, argv = argv[0], argv[1], argv[2:]
        if flag == "--env":
            env_file = value
        else:
            cwd = value
    if not env_file or not argv:
        raise SystemExit(__doc__)

    for name, value in read_env(env_file).items():
        os.environ.setdefault(name, value)
    install = Path(env_file).resolve().parent
    tmp = install / "tmp"
    tmp.mkdir(exist_ok=True)
    for name in ("TEMP", "TMP"):
        os.environ[name] = str(tmp)

    if cwd:
        os.chdir(cwd)
        sys.path.insert(0, str(Path(cwd).resolve()))
    module, *rest = argv
    sys.argv = [module, *rest]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
