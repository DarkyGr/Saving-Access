"""
Monitoring and alerts for the local installation (task 35.3, Requirement 20).

Run every 15 minutes by the scheduled task ``\\Save-Pass\\Monitor``
(``python -m app.cli monitor ...``). Each run:

- checks that the API and the IIS site answer ``/api/health``, that the newest
  backup is recent and did not fail, that the weekly restore test passed,
  that the scheduled tasks ended well and that the backup disk has room;
- emails every active Admin when a problem appears, again every 24 hours while
  it lasts, and once more when everything is back to normal;
- trims the logs so they never fill the disk.

The checks only read files, ask the health endpoints and read the tasks'
last result; they never touch the data.
"""

from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKUP_MAX_AGE = timedelta(hours=26)
RESTORE_MAX_AGE = timedelta(days=8)
MIN_FREE_BYTES = 2 * 1024**3
REMIND_EVERY = timedelta(hours=24)
TASKS = ("Backup", "Restore test", "Reminders")
# Task Scheduler results that are not failures: 0 = success, 0x41301 =
# running, 0x41303 = not run yet, 0x41325 = queued.
TASK_OK = {0, 0x41301, 0x41303, 0x41325}
ROTATE_BYTES = 10 * 1024**2
KEEP_ROTATED = 3
IIS_LOG_DAYS = 30


@dataclass(frozen=True)
class Problem:
    key: str
    en: str
    es: str


def _now() -> datetime:
    return datetime.now(UTC)


# ── Checks ───────────────────────────────────────────────────────────────


def check_health(url: str, key: str, *, insecure: bool = False, opener=urllib.request.urlopen) -> list[Problem]:
    """``/api/health`` must answer {"status": "ok"}. The IIS check uses
    ``insecure`` because it calls this same machine through its own
    certificate, which the service account may not trust."""
    context = ssl._create_unverified_context() if insecure else None  # noqa: S323 — loopback only
    try:
        with opener(url, timeout=10, context=context) as response:
            body = json.loads(response.read().decode("utf-8"))
        if body.get("status") == "ok":
            return []
        detail = body.get("status", "?")
    except Exception as error:  # noqa: BLE001 — any failure is the finding
        detail = type(error).__name__
    return [Problem(key, f"{url} does not answer correctly ({detail}).", f"{url} no responde bien ({detail}).")]


def _last_line(path: Path) -> str:
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    except OSError:
        return ""
    return lines[-1] if lines else ""


def check_backups(folder: Path, now: datetime | None = None) -> list[Problem]:
    now = now or _now()
    problems: list[Problem] = []
    backups = sorted(folder.glob("savepass-*.dump.enc"), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
    if not backups:
        problems.append(Problem("backup", f"There is no backup in {folder}.", f"No hay ningún respaldo en {folder}."))
    else:
        age = now - datetime.fromtimestamp(backups[-1].stat().st_mtime, UTC)
        if age > BACKUP_MAX_AGE:
            hours = int(age.total_seconds() // 3600)
            problems.append(Problem("backup", f"The newest backup is {hours} hours old.", f"El respaldo más reciente tiene {hours} horas."))
    last = _last_line(folder / "backup.log")
    if last.startswith("FAILED"):
        problems.append(Problem("backup-failed", f"The last backup failed: {last[7:][:200]}", f"El último respaldo falló: {last[7:][:200]}"))
    restore_log = folder / "restore-test.log"
    if restore_log.exists():
        last = _last_line(restore_log)
        age = now - datetime.fromtimestamp(restore_log.stat().st_mtime, UTC)
        if "FAILED" in last:
            problems.append(Problem("restore", f"The last restore test failed: {last[:200]}", f"La última prueba de restauración falló: {last[:200]}"))
        elif age > RESTORE_MAX_AGE:
            problems.append(Problem("restore", "The weekly restore test has not run for more than 8 days.", "La prueba de restauración semanal no corre desde hace más de 8 días."))
    return problems


def check_tasks(results: dict[str, int | None]) -> list[Problem]:
    """*results*: last result of each scheduled task (None = unknown)."""
    problems = []
    for name, code in results.items():
        if code is not None and code not in TASK_OK:
            problems.append(Problem(f"task:{name}", f"The task {name} ended with error 0x{code:X}.", f"La tarea {name} terminó con error 0x{code:X}."))
    return problems


def task_results(folder: str = "\\Save-Pass\\", runner=subprocess.run) -> dict[str, int | None]:
    """Last result of each task, from Task Scheduler (Windows only)."""
    script = (
        f"Get-ScheduledTask -TaskPath '{folder}' | ForEach-Object {{ "
        "$i = $_ | Get-ScheduledTaskInfo; \"$($_.TaskName)`t$($i.LastTaskResult)\" }"
    )
    try:
        out = runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=60, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    results: dict[str, int | None] = {}
    for line in out.splitlines():
        name, _, code = line.partition("\t")
        if name in TASKS:
            try:
                results[name] = int(code)
            except ValueError:
                results[name] = None
    return results


def check_disk(folder: Path, usage=shutil.disk_usage) -> list[Problem]:
    try:
        free = usage(folder).free
    except OSError:
        return []
    if free >= MIN_FREE_BYTES:
        return []
    gb = free / 1024**3
    return [Problem("disk", f"Only {gb:.1f} GB free where the backups are kept.", f"Solo quedan {gb:.1f} GB libres donde se guardan los respaldos.")]


# ── Log retention ────────────────────────────────────────────────────────


def rotate(path: Path, *, max_bytes: int = ROTATE_BYTES, keep: int = KEEP_ROTATED) -> bool:
    """Move a big log aside (.1, .2 …). A log held open by a running process
    is copied and emptied instead. Returns True when it rotated."""
    try:
        if not path.exists() or path.stat().st_size <= max_bytes:
            return False
        path.with_name(f"{path.name}.{keep}").unlink(missing_ok=True)
        for n in range(keep - 1, 0, -1):
            older = path.with_name(f"{path.name}.{n}")
            if older.exists():
                older.replace(path.with_name(f"{path.name}.{n + 1}"))
        try:
            path.replace(path.with_name(f"{path.name}.1"))
        except PermissionError:
            shutil.copyfile(path, path.with_name(f"{path.name}.1"))
            with path.open("r+b") as handle:
                handle.truncate(0)
        return True
    except OSError:
        return False


def prune(folder: Path, *, days: int = IIS_LOG_DAYS, now: float | None = None) -> int:
    """Delete ``*.log`` files under *folder* older than *days*."""
    if not folder.is_dir():
        return 0
    limit = (now or time.time()) - days * 86400
    removed = 0
    for path in folder.rglob("*.log"):
        try:
            if path.stat().st_mtime < limit:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


# ── State and alerts ─────────────────────────────────────────────────────


def decide(problems: list[Problem], state: dict, now: datetime | None = None) -> tuple[str | None, dict]:
    """``("alert" | "resolved" | None, new_state)``: alert on new problems
    or every 24 hours while they last; "resolved" once when all are gone."""
    now = now or _now()
    keys = sorted(p.key for p in problems)
    before = state.get("problems", [])
    last_sent = state.get("last_alert")
    new_state = {"problems": keys, "last_alert": last_sent}
    if keys:
        due = last_sent is None or now - datetime.fromisoformat(last_sent) >= REMIND_EVERY
        if set(keys) - set(before) or due:
            new_state["last_alert"] = now.isoformat()
            return "alert", new_state
        return None, new_state
    if before:
        new_state["last_alert"] = None
        return "resolved", new_state
    return None, new_state


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def alert_email(admin, problems: list[Problem], action: str):
    """The email for one Admin, in their language."""
    from app.services.email_sender import OutgoingEmail

    spanish = (admin.preferred_language or "en").lower().startswith("es")
    name = admin.display_name or admin.username
    when = _now().strftime("%Y-%m-%d %H:%M")
    if action == "resolved":
        subject = "Save-Pass: todo vuelve a funcionar" if spanish else "Save-Pass: back to normal"
        body = (
            f"Hola {name}:\n\nDesde el {when} (UTC) todas las revisiones de Save-Pass están bien de nuevo.\n"
            if spanish
            else f"Hello {name},\n\nSince {when} (UTC) every Save-Pass check is fine again.\n"
        )
        return OutgoingEmail(to=admin.email, subject=subject, body=body)
    lines = "\n".join(f"- {p.es if spanish else p.en}" for p in problems)
    if spanish:
        subject = f"Save-Pass: alerta ({len(problems)} problema{'s' if len(problems) != 1 else ''})"
        body = (
            f"Hola {name}:\n\nLa revisión automática de Save-Pass del {when} (UTC) encontró:\n\n{lines}\n\n"
            "Mira la Guía técnica (Solución de problemas). Recibirás este aviso cada 24 horas mientras siga, "
            "y otro cuando se resuelva.\n"
        )
    else:
        subject = f"Save-Pass alert ({len(problems)} problem{'s' if len(problems) != 1 else ''})"
        body = (
            f"Hello {name},\n\nThe automatic Save-Pass check of {when} (UTC) found:\n\n{lines}\n\n"
            "See the Technical guide (Troubleshooting). You get this every 24 hours while it lasts, "
            "and once more when it is solved.\n"
        )
    return OutgoingEmail(to=admin.email, subject=subject, body=body)
