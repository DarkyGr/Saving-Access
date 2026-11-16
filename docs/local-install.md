# Local installation on Windows (task 36)

Save-Pass installed permanently on this laptop, published with HTTPS to the
home network, following the same model as Savings Tool's local operation
(phase 8). The Docker production stack (`docker-compose.prod.yml`) stays for a
real server; this guide is for running it on the Windows laptop itself.

## Pieces

| Piece | Where | How |
|---|---|---|
| App folder | `Y:\Apps\Save-Pass` | `app\` backend code (previous version in `app.old\`), `web\` built SPA + `web.config`, `python\` private runtime, `ops\` jobs, `logs\`, `tmp\`, `certs\`, `data\postgres\`. Nothing on `C:`. |
| Settings | `Y:\Apps\Save-Pass\.env.production` | Template with fresh secrets written by the first release. ACL: Administrators, SYSTEM, Network Service (read). Keep `FERNET_KEY` and `BACKUP_KEY` in your password manager: without `FERNET_KEY` the saved passwords cannot be recovered, even from a backup. |
| Python | `Y:\Apps\Save-Pass\python` | Copy of the Python that ran the release (without its packages) plus `backend\requirements.txt`. Needed because the tasks run as Network Service, which cannot read a Python installed for one user under `C:\Users`. Reinstalled only when the Python version or the requirements change. |
| API | Task `\Save-Pass\API` at startup (30 s delay), Network Service, restarted every minute if it stops | `python ops\run.py --env .env.production --cwd app uvicorn app.main:app --host 127.0.0.1 --port 8010`; output to `logs\api.log`. One worker, in-memory rate limits. |
| Database | Own PostgreSQL 18 cluster in `data\postgres`, service `savepass-postgres`, `127.0.0.1:5435`, scram only | Roles `savepass_migrator` (owner, runs migrations), `savepass_app` (DML only, Requirement 9.9), `savepass_backup` (`pg_read_all_data` + CREATEDB for the restore test). Other PostgreSQL services (`postgresql-x64-18`, `savings-postgres`) are not touched. |
| HTTPS | IIS site **Save-Pass** on **8443** (443 is Savings Tool's site) | Serves `web\` and proxies `/api/*` to `127.0.0.1:8010` with URL Rewrite + ARR. Same security headers as the Caddyfile (HSTS, CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy`); `Cache-Control: no-store` on the API; API errors pass through as JSON. IIS logs to `Backup\logs\iis`. |
| Client IP | IIS sets `X-Client-IP = {REMOTE_ADDR}` | The API trusts it only from 127.0.0.1 (`CLIENT_IP_HEADER`), so login limits are per device. ARR's `X-Forwarded-For` carries `ip:port` and is not used. |
| Certificate | mkcert with **Savings Tool's authority** (`Y:\Code\Git\Repos\Savings-Tool\Backup\certs`) | The laptop and the phone already trust it. Names: host of `APP_BASE_URL`, hosts of `TRUSTED_ORIGINS`, LAN IP, `localhost`, `127.0.0.1`. Thumbprint in `certs\thumbprint.txt`. Without that authority, a new one is made in `Backup\certs`. |
| Network | Firewall rule TCP 8443, Private profile only | The home Wi-Fi must be Private. |
| Power | Plugged in: never sleep, lid does nothing | Same as Savings Tool. |
| Backup | Task `\Save-Pass\Backup` daily 02:30 (or at the next start) | `ops\backup.py`: `pg_dump -Fc` as `savepass_backup`, AES-256-GCM with `BACKUP_KEY` to `Backup\db\savepass-YYYYMMDD-HHmm.dump.enc`; the plain dump never stays; keeps 14 daily + the newest of 12 months. |
| Restore test | Task `\Save-Pass\Restore test` Sundays 03:30 | `ops\restore_test.py`: decrypts the newest backup, restores it into `savepass_restore_test_*`, compares the rows of every table with the live database, drops the scratch database; log in `Backup\db\restore-test.log`. |
| Reminders | Task `\Save-Pass\Reminders` daily 08:05 and 5 min after startup | `app.cli send-verification-reminders`; does nothing while email verification is off. |

Task times are 30 minutes after Savings Tool's, so the two never back up at once.

## Ports on this laptop

| Port | Who |
|---|---|
| 443 | IIS — Savings Tool |
| **8443** | IIS — Save-Pass |
| 3000 / 3001 | Savings Tool app / its development server |
| 5432 | `postgresql-x64-18` (native service) |
| 5433 / 5434 | Savings Tool development / installed database |
| **5435** | Save-Pass installed database |
| **5436** | Save-Pass development database (Docker) |
| **8010** | Save-Pass installed API (only 127.0.0.1) |
| 8000 / 5173 | Save-Pass development API / Vite (Docker) |
| 8001 / 5174 | Save-Pass E2E tests |

## Install (in this order)

Already present on this laptop for Savings Tool: IIS, URL Rewrite 2.1, ARR 3.0,
`Y:\Code\Claude\tools\mkcert.exe`, Wi-Fi as Private.

1. `powershell -ExecutionPolicy Bypass -File ops\windows\00-check.ps1` (changes nothing).
2. `python scripts\release.py --to Y:\Apps\Save-Pass` → writes `.env.production.example`. Review `APP_BASE_URL` (`https://<laptop>.local:8443`); for the phone add `TRUSTED_ORIGINS=https://<laptop IP>:8443`. Save `FERNET_KEY`, `BACKUP_KEY` and the passwords in your password manager; rename to `.env.production`.
3. **As administrator**: `ops\windows\01-postgres.ps1` → keep the `postgres` password it shows once.
4. `python scripts\release.py --to Y:\Apps\Save-Pass` (runtime, frontend build, settings check, migrations, install).
5. First admin, **from an administrator terminal** (the settings file is admin-only after step 6):
   `powershell -ExecutionPolicy Bypass -File ops\windows\with-production.ps1 create-admin --username admin --email you@example.com`
6. **As administrator**: `02-certificate.ps1 -Ip <laptop IP>`, `03-iis.ps1`, `04-network-power.ps1`, `05-tasks.ps1` (starts the API and checks `/api/health`).
7. Open `https://<laptop>.local:8443` on the laptop and the phone; run a first backup: `Start-ScheduledTask -TaskPath "\Save-Pass\" -TaskName Backup`.

## Update

From an **administrator** terminal: `python scripts\release.py --to Y:\Apps\Save-Pass`.
It checks the settings, stops the API task and waits until its Python has
exited (killing it after 15 s), migrates, swaps `app` (retrying while Windows
still holds the folder; on failure the previous app is put back and the task
restarted) (the
previous one stays in `app.old`), syncs `web\` (new files first, `index.html`
last, stale files removed; the folder is not renamed because IIS watches it)
and starts the task again.

## Other tools

| Need | Run |
|---|---|
| The laptop's IP changed | `ops\windows\update-ip.cmd` (asks for administrator): updates `TRUSTED_ORIGINS`, new certificate with the same authority, IIS, restarts the API. |
| Lost the `postgres` password | `ops\windows\reset-postgres-password.cmd`: lets only `postgres` from 127.0.0.1 in without a password for a few seconds, changes it, restores `pg_hba.conf` even on error. |
| Any CLI command on the installation | `ops\windows\with-production.ps1 <command> [args]` (e.g. `verify-email --username alice`, `rotate-fernet-key --dry-run`). |

## Restore for real (disaster)

1. Stop the task `API`.
2. Decrypt the backup: `Y:\Apps\Save-Pass\python\python.exe -c "import sys; sys.path.insert(0, r'Y:\Apps\Save-Pass\ops'); import oplib; from pathlib import Path; s = oplib.read_env(r'Y:\Apps\Save-Pass\.env.production'); oplib.decrypt_file(Path(sys.argv[1]), Path(sys.argv[2]), oplib.backup_key(s))" <backup.enc> <out.dump>` (or run `ops\restore_test.py` first to validate it).
3. As `postgres`: `DROP DATABASE savepass; CREATE DATABASE savepass OWNER savepass_migrator;` then the grants of `01-postgres.ps1` (from `REVOKE CONNECT` on).
4. `pg_restore --no-owner --no-privileges --role=savepass_migrator -d savepass <out.dump>` (as `savepass_migrator`), then delete `<out.dump>`.
5. Start `API` and check `/api/health`.

## Development (Docker), one double click

`ops\local\start-local.cmd` / `stop-local.cmd`, same as Savings Tool:

- **Start**: stops the previous run's timer, starts Docker if needed (without its window), `docker compose down` + `up -d --build --wait` (PostgreSQL on 127.0.0.1:5436, API on 8000 with the migrations, Vite on 5173), and a hidden 30-minute timer that stops everything.
- **Stop**: `docker compose down` (the data volume stays) and Docker only if the script started it.
- Logs: `Backup\logs\local-dev.log` and `local-control.log` (rewritten each start); state in `Backup\tmp\local-dev.json`.
- Needs a `.env` (copy `.env.example`, fill in `JWT_SECRET` and `FERNET_KEY`).

## Verified

- Rehearsal without administrator rights (2026-11-14): a cluster with the
  exact SQL of `01-postgres.ps1`, two releases (install and update), the API
  running from the installed folder with its own Python, register / save /
  reveal / search, per-device login limits through `X-Client-IP`, role
  privileges (API cannot drop, create, truncate or alter; backup cannot
  write), `with-production.ps1 create-admin`, encrypted backup and restore
  test. All PowerShell scripts parse in Windows PowerShell 5.1 and 7;
  `00-check.ps1` runs.
- **Not verified yet** (needs administrator, the owner runs them): the
  `savepass-postgres` service, the certificate, the IIS site on 8443 (rewrite
  rules and headers of `web.config`), the firewall rule and the scheduled
  tasks running as Network Service.
