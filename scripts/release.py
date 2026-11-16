"""
Builds Save-Pass and installs it outside the repository (local installation,
task 36). Same model as Savings Tool's `npm run release`.

    python scripts/release.py --to Y:\\Apps\\Save-Pass [--skip-build] [--skip-migrate]

<to>\\.env.production holds the production settings. The first run writes
<to>\\.env.production.example with fresh secrets and stops. Then:

  1. a private Python runtime in <to>\\python (a copy of this interpreter,
     without its packages) with the backend requirements, because the
     scheduled tasks run as Network Service, which cannot read a Python
     installed for one user under C:\\Users,
  2. the frontend built for the same origin (frontend\\dist-release),
  3. <to>\\app.new with the backend; the settings are checked with the
     backend's own validate_settings and the migrations applied with the
     migrator role,
  4. the API task stopped, app.new swapped in (the previous one stays in
     app.old), <to>\\web synced (index.html last) with its web.config, the
     operation jobs copied to <to>\\ops, the task started again.

Logs, backups, data and settings in <to> are never touched.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"
TASK = r"\Save-Pass\API"
REQUIRED = (
    "DATABASE_URL", "DATABASE_URL_MIGRATOR", "BACKUP_DATABASE_URL", "JWT_SECRET",
    "FERNET_KEY", "BACKUP_KEY", "APP_BASE_URL", "API_PORT", "HTTPS_PORT",
)
# Not needed to run the app; left out of the private runtime copy.
RUNTIME_SKIP = {"site-packages", "Scripts", "Doc", "tcl", "Tools", "__pycache__", "test", "idlelib", "tkinter", "turtledemo"}

sys.path.insert(0, str(REPO / "ops"))
from oplib import read_env  # noqa: E402


def example_settings() -> str:
    host = socket.gethostname().lower()

    def password() -> str:
        return secrets.token_urlsafe(24)

    fernet = base64.urlsafe_b64encode(os.urandom(32)).decode()
    return "\n".join([
        "# Production settings of the local Save-Pass installation. Never commit this file.",
        "ENVIRONMENT=production",
        "# Address people open (the IIS site with its certificate). 443 belongs to Savings Tool.",
        f"APP_BASE_URL=https://{host}.local:8443",
        "# Other addresses, comma-separated (e.g. https://192.168.1.50:8443 for the phone).",
        "# ops\\windows\\update-ip.cmd keeps the home-network one up to date.",
        "TRUSTED_ORIGINS=",
        "HTTPS_PORT=8443",
        "# The API listens only on this machine; IIS publishes it.",
        "API_PORT=8010",
        "# Own PostgreSQL cluster (ops\\windows\\01-postgres.ps1 creates these roles with these passwords).",
        f"DATABASE_URL=postgresql://savepass_app:{password()}@127.0.0.1:5435/savepass",
        f"DATABASE_URL_MIGRATOR=postgresql://savepass_migrator:{password()}@127.0.0.1:5435/savepass",
        "# Read-only role of the backups (it can also create the restore-test database).",
        f"BACKUP_DATABASE_URL=postgresql://savepass_backup:{password()}@127.0.0.1:5435/savepass",
        "# Fresh secrets for this file: keep a copy of FERNET_KEY and BACKUP_KEY in your password manager.",
        "# Without FERNET_KEY the saved passwords cannot be recovered, even from a backup.",
        f"JWT_SECRET={secrets.token_urlsafe(48)}",
        "JWT_ALGORITHM=HS256",
        "JWT_EXPIRE_MINUTES=15",
        "REFRESH_EXPIRE_HOURS=8",
        f"FERNET_KEY={fernet}",
        f"BACKUP_KEY={base64.b64encode(os.urandom(32)).decode()}",
        "COOKIE_SECURE=true",
        "COOKIE_SAMESITE=strict",
        "# IIS sends the device's address in this header (per-device rate limits).",
        "CLIENT_IP_HEADER=X-Client-IP",
        "RATE_LIMIT_ENABLED=true",
        "RATE_LIMIT_STORAGE=memory://",
        "# Spec Phase 2 (see .env.prod.example): off until SMTP is configured.",
        "EMAIL_VERIFICATION_ENABLED=false",
        "EMAIL_BACKEND=console",
        "",
    ])


def check_settings(settings: dict[str, str], env_file: Path) -> None:
    for name in REQUIRED:
        if not settings.get(name) or "CHANGE_ME" in settings[name]:
            raise SystemExit(f"{env_file}: {name} is missing or still CHANGE_ME.")
    for name in ("API_PORT", "HTTPS_PORT"):
        if not settings[name].isdigit():
            raise SystemExit(f"{env_file}: {name} must be a port number.")


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"> {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        raise SystemExit(f"Failed: {' '.join(cmd)}")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ensure_runtime(target: Path, work_env: dict[str, str]) -> Path:
    """Private Python with the backend requirements; reinstalled only when
    the interpreter version or the requirements change."""
    runtime = target / "python"
    exe = runtime / ("python.exe" if os.name == "nt" else "bin/python3")
    marker = runtime / "save-pass-runtime.txt"
    wanted = f"{sys.version.split()[0]} {file_hash(BACKEND / 'requirements.txt')}"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == wanted and exe.exists():
        print("Python runtime is up to date.")
        return exe

    base = Path(sys.base_prefix)
    if not marker.exists() or not exe.exists() or not marker.read_text(encoding="utf-8").startswith(sys.version.split()[0] + " "):
        print(f"Copying the Python runtime from {base}...")
        shutil.rmtree(runtime, ignore_errors=True)
        shutil.copytree(base, runtime, ignore=lambda _d, names: [n for n in names if n in RUNTIME_SKIP])
        (runtime / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
        run([str(exe), "-m", "ensurepip", "--default-pip"], cwd=target, env=work_env)
    print("Installing the backend requirements...")
    run([str(exe), "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check",
         "--no-warn-script-location", "-r", str(BACKEND / "requirements.txt")], cwd=target, env=work_env)
    marker.write_text(wanted + "\n", encoding="utf-8")
    return exe


def build_frontend(work_env: dict[str, str]) -> Path:
    out = FRONTEND / "dist-release"
    env = {**work_env, "VITE_API_URL": ""}  # same origin: IIS serves the SPA and proxies /api
    npm = "npm.cmd" if os.name == "nt" else "npm"
    run([npm, "run", "build", "--", "--outDir", "dist-release", "--emptyOutDir"], cwd=FRONTEND, env=env)
    if not (out / "index.html").exists():
        raise SystemExit(f"{out}\\index.html not found after the build.")
    return out


def copy_backend(dest: Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    dest.mkdir(parents=True)
    shutil.copytree(BACKEND / "app", dest / "app", ignore=ignore)
    shutil.copytree(BACKEND / "migrations", dest / "migrations", ignore=ignore)
    shutil.copy2(BACKEND / "alembic.ini", dest / "alembic.ini")


def sync_web(dist: Path, web: Path, api_port: str) -> None:
    """Mirror *dist* into *web* without renaming the IIS site folder (IIS
    watches it): new files first, index.html last, then stale files go."""
    web.mkdir(parents=True, exist_ok=True)
    wanted: set[Path] = set()
    for src in sorted(dist.rglob("*"), key=lambda p: p.name == "index.html"):
        rel = src.relative_to(dist)
        wanted.add(rel)
        dest = web / rel
        if src.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    template = (REPO / "deploy" / "iis" / "web.config.template").read_text(encoding="utf-8")
    (web / "web.config").write_text(template.replace("{{API_PORT}}", api_port), encoding="utf-8")
    wanted.add(Path("web.config"))
    for path in sorted(web.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        rel = path.relative_to(web)
        if rel in wanted:
            continue
        if path.is_dir():
            if not any(path.iterdir()):
                path.rmdir()
        else:
            path.unlink()


def schtasks(verb: str) -> bool:
    if os.name != "nt":
        return False
    return subprocess.run(["schtasks", verb, "/TN", TASK], capture_output=True).returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", required=True)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-migrate", action="store_true")
    args = parser.parse_args(argv)

    target = Path(args.to).resolve()
    if re.match(r"^[cC]:", str(target)):
        raise SystemExit("The app must not be installed on C:.")
    target.mkdir(parents=True, exist_ok=True)

    env_file = target / ".env.production"
    if not env_file.exists():
        example = target / ".env.production.example"
        example.write_text(example_settings(), encoding="utf-8")
        print(f"Wrote {example}. Review it, keep FERNET_KEY and BACKUP_KEY in your password manager,")
        print("rename it to .env.production and run ops\\windows\\01-postgres.ps1 as administrator.")
        return 0
    settings = read_env(env_file)
    check_settings(settings, env_file)

    tmp = target / "tmp"
    tmp.mkdir(exist_ok=True)
    work_env = {**os.environ, "TEMP": str(tmp), "TMP": str(tmp), "PIP_NO_INPUT": "1"}

    python = ensure_runtime(target, work_env)
    dist = FRONTEND / "dist-release"
    if not args.skip_build:
        print("Building the frontend...")
        dist = build_frontend(work_env)
    elif not (dist / "index.html").exists():
        raise SystemExit("--skip-build needs an earlier build in frontend\\dist-release.")

    fresh = target / "app.new"
    shutil.rmtree(fresh, ignore_errors=True)
    copy_backend(fresh)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip() or "unknown"
    (fresh / "VERSION").write_text(f"{commit} {datetime.now(UTC).isoformat(timespec='seconds')}\n", encoding="utf-8")

    app_env = {**work_env, **settings}
    print("Checking the settings...")
    run([str(python), "-c", "from app.security import validate_settings; validate_settings()"], cwd=fresh, env=app_env)
    if not args.skip_migrate:
        print("Applying migrations to the production database...")
        run([str(python), "-m", "alembic", "upgrade", "head"], cwd=fresh,
            env={**app_env, "DATABASE_URL": settings["DATABASE_URL_MIGRATOR"]})

    stopped = schtasks("/End")
    current, old = target / "app", target / "app.old"
    shutil.rmtree(old, ignore_errors=True)
    if current.exists():
        current.rename(old)
    fresh.rename(current)
    sync_web(dist, target / "web", settings["API_PORT"])
    ops = target / "ops"
    shutil.rmtree(ops, ignore_errors=True)
    shutil.copytree(REPO / "ops", ops, ignore=lambda d, names: [
        n for n in names if n in {"windows", "local", "__pycache__"}
    ])
    (target / "logs").mkdir(exist_ok=True)

    if stopped and schtasks("/Run"):
        print(f"Installed {commit} and restarted the API task.")
    else:
        print(f'Installed {commit}. Start the API task (as administrator): schtasks /Run /TN "{TASK}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
