# Save-Pass — Password Manager

A full-stack secure password manager web application. Users can store, search, reveal, edit, and delete credentials for any website. All encryption happens exclusively on the backend — the frontend never sees an encryption key or a plaintext password from the database.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript, Vite, Tailwind CSS, react-i18next |
| Backend | Python 3.11, FastAPI, SQLAlchemy ORM |
| Database | PostgreSQL 15 |
| Auth | JWT access token (HS256, 15 min, in memory) + rotating refresh token in an httpOnly cookie |
| Encryption | Fernet / AES-128-CBC (`cryptography` library) |
| Password hashing | bcrypt |
| Migrations | Alembic |
| Rate limiting | slowapi |
| Containerization | Docker + Docker Compose |

---

## Features

- **Secure credential storage** — passwords are Fernet-encrypted before reaching the database; plaintext never persists.
- **Password confirmation prompt** — every sensitive operation (save, reveal, edit, delete) requires re-entering the account password.
- **Timed password reveal** — revealed passwords are automatically masked after 60 seconds.
- **Search** — case-insensitive partial match on website name or email/username.
- **Role-based access control** — one role per account (User or Admin), each with fixed per-action permissions; the Admin manages accounts but never sees anyone else's passwords.
- **Audit log** — every INSERT, SELECT, UPDATE, and DELETE is recorded with the user and timestamp.
- **Internationalization** — English (default) and Spanish, switchable without reloading the page.
- **Responsive** — works from 320 px mobile to 1920 px desktop.

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Docker Desktop | 24+ |
| Docker Compose | v2 (bundled with Docker Desktop) |
| Python | 3.11+ (only for local development without Docker) |
| Node.js | 18+ (only for local development without Docker) |

---

## Quick Start (Docker — recommended)

### 1. Clone the repository

```bash
git clone <repo-url>
cd save-pass
```

### 2. Create the environment file

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```env
# Generate with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=<your-fernet-key>

# A random secret used to sign JWTs
JWT_SECRET=<your-jwt-secret>

# Leave defaults unless you change docker-compose.yml
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=15
CORS_ORIGINS=http://localhost:5173
DATABASE_URL=postgresql://savepass_user:savepass_password@localhost:5436/savepass
```

### 3. Start all services

```bash
make up
```

This builds and starts three containers: `db` (PostgreSQL 15), `backend` (FastAPI on port 8000), and `frontend` (Vite dev server on port 5173).

### 4. Open the app

```
http://localhost:5173
```

The backend API is available at `http://localhost:8000`. Interactive API docs at `http://localhost:8000/docs`.

### 5. Create the first Admin

Every new sign-up is a **User** (view, save, edit, delete and reveal their own credentials). An **Admin** also manages accounts and roles; the first one is created with `python -m app.cli create-admin`.

Admin accounts cannot be created from the sign-up page. Create the first one from the command line:

```bash
make create-admin USERNAME=admin EMAIL=admin@example.com
# without Docker: cd backend && python -m app.cli create-admin --username admin --email admin@example.com
```

You will be asked for the password twice (or set `ADMIN_PASSWORD`). To give an existing account the Admin role: `python -m app.cli promote --username alice`.

### Stop

```bash
make down
```

---

## Production Deployment

`docker-compose.prod.yml` runs the hardened stack: **Caddy** (HTTPS with automatic certificates, security headers, serves the built frontend and proxies `/api`), a one-shot **migrate** service, the **backend** (2 workers) connected as the least-privilege `app_user` database role, **Redis** for shared rate-limit counters, **PostgreSQL**, a **backup** service (daily `pg_dump`, kept 14 days) and a **scheduler** for verification reminders. Only ports 80/443 are published.

```bash
cp .env.prod.example .env.prod      # set SITE_ADDRESS, passwords, FERNET_KEY, JWT_SECRET
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend \
  python -m app.cli create-admin --username admin --email admin@example.com
```

Point your domain's DNS to the server before starting so Caddy can obtain the certificate. Backups are written to the `backups` volume; copy them off the server and keep `FERNET_KEY` stored separately: without the key, saved passwords cannot be recovered. `make backup` takes one now and `./scripts/restore-backup.sh <dump>` restores one ([details](ARCHITECTURE.md#backups-and-restore)). Key rotation without downtime is described in [ARCHITECTURE.md](ARCHITECTURE.md#6-fernet-key-management-and-rotation).

To try the production stack locally (self-signed certificate on `https://localhost`, everything removed afterwards): `make smoke-prod`.

---

## Local Installation (Windows, this laptop)

Save-Pass can run permanently on the Windows laptop like Savings Tool: its own PostgreSQL service, the API as a scheduled task, IIS with HTTPS on `https://<laptop>.local:8443` for the home network (phone included), daily encrypted backups with a weekly restore test. Step-by-step guide: [`docs/local-install.md`](docs/local-install.md).

```bash
python scripts/release.py --to Y:\Apps\Save-Pass     # first run writes the settings template
```

For development there is a one-click start/stop: `ops\local\start-local.cmd` / `stop-local.cmd` (Docker, stops by itself after 30 minutes).

---

## Local Development (without Docker)

### Backend

```bash
make install-backend       # pip install -r backend/requirements.txt
# start a local PostgreSQL instance and set DATABASE_URL in .env
cd backend
alembic upgrade head       # create / update the schema
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
make install-frontend      # npm install inside frontend/
cd frontend
npm run dev
```

### Database migrations

The schema is managed only by Alembic (`backend/migrations`). Docker runs `alembic upgrade head` before starting the API.

```bash
cd backend
alembic upgrade head                              # apply
alembic revision --autogenerate -m "add x"        # after changing app/models.py
python db/generate_schema_sql.py                  # refresh the reference db/schema.sql
```

**Database created before migrations existed** (tables made by the old automatic `create_all`): adopt it once, then upgrade as usual:

```bash
alembic stamp 0001_baseline
alembic upgrade head
```

---

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/savepass` |
| `FERNET_KEY` | 32-byte URL-safe base64 key for credential encryption (`"<new>,<old>"` during a key rotation) | _(generated)_ |
| `JWT_SECRET` | Secret used to sign and verify JWTs | _(random string)_ |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `JWT_EXPIRE_MINUTES` | Token lifetime in minutes | `15` |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins | `http://localhost:5173` |
| `REFRESH_EXPIRE_HOURS` | How long a login lasts without re-entering the password | `8` |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | Refresh cookie flags | `true` / `strict` |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_STORAGE` | Rate limiting on/off and its store (Redis in production, shared by all workers) | `true` / `memory://` |
| `RATE_LIMIT_FALLBACK` | Per-IP limit used in memory while Redis is unreachable | `60/minute` |
| `WEB_CONCURRENCY` | API worker processes (production) | `2` |
| `BACKUP_INTERVAL_HOURS` / `BACKUP_RETENTION_DAYS` | Production backup schedule | `24` / `14` |
| `VERIFICATION_REMINDER_DAYS` | Reminder emails N days before the deactivation deadline (empty = none) | `7,1` |
| `EMAIL_VERIFICATION_ENABLED` | Require email verification within 30 days of sign-up (spec Phase 2) | `false` |
| `APP_BASE_URL` | Public frontend URL used in verification links (required when verification is on; set automatically in production) | `http://localhost:5173` |
| `EMAIL_BACKEND` | `console` (print), `smtp` or `file` (`EMAIL_OUTBOX_DIR`) | `console` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_SECURITY` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` | Mail server for `EMAIL_BACKEND=smtp` (`SMTP_SECURITY`: `starttls`, `ssl` or `none`) | `smtp.example.com` / `587` / `starttls` |
| `HCAPTCHA_SITE_KEY` / `HCAPTCHA_SECRET` | hCaptcha on the login page; set both or neither | _(empty = off)_ |

The backend **refuses to start** if `JWT_SECRET` is missing or shorter than 32 characters, if `FERNET_KEY` is not a valid Fernet key, or if the optional email verification / CAPTCHA settings are incomplete. Generate a JWT secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> **Never commit `.env`.** Only `.env.example` (without real values) belongs in version control.

To generate a Fernet key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Running Tests

All of the checks below run in GitHub Actions on every push (`.github/workflows/ci.yml`), plus migrations and API tests on PostgreSQL 15 and the production smoke test.

### Lint

```bash
make lint      # ruff (backend) + eslint (frontend)
```

### Backend (pytest + Hypothesis property tests)

```bash
make test-backend
# equivalent to: cd backend && python -m pytest tests/ -v
```

The backend test suite includes:
- Unit tests for `AuthService`, `EncryptorService`, `AuditService` and the role permissions.
- Property-based tests (Hypothesis) covering 14 correctness properties with 100–200 iterations each (ownership isolation, search filter correctness, wrong-password rejection, encryption invariant, etc.).
- Integration tests for full credential lifecycle and admin permission flow.

### Frontend (Vitest + React Testing Library)

```bash
make test-frontend
# equivalent to: cd frontend && npm run test
```

Covers: `PasswordInput` Eye_Toggle, `PasswordConfirmModal` callbacks, `useVisibilityTimer` with fake timers, `ProtectedRoute` redirects, `LanguageToggle` language switching, the `AppLayout` header.

### End-to-end (Playwright)

```bash
make test-e2e
# first time only: cd frontend && npx playwright install chromium
```

Playwright starts its own backend (port 8001, throwaway SQLite database — or a disposable PostgreSQL database given in `E2E_POSTGRES_URL`) and frontend (port 5174), then drives a real browser through sign-up, login, save, search, reveal, edit, delete, language switch, logout and the admin role change. No mocks and no Docker required.

---

## Project Structure

```
save-pass/
├── .env.example               # Environment variable template
├── docker-compose.yml         # Development: db, backend, frontend
├── docker-compose.prod.yml    # Production: Caddy (HTTPS), migrate, backend as app_user, db
├── .env.prod.example          # Production settings template
├── deploy/                    # Caddyfile + web image, PostgreSQL app_user init script
├── scripts/smoke-prod.sh      # End-to-end check of the production stack
├── .github/workflows/ci.yml   # CI: lint, audits, tests (SQLite + PostgreSQL), E2E, prod smoke
├── Makefile                   # Common dev commands
├── ARCHITECTURE.md            # Technical deep-dive (flows, schema, key rotation)
├── CLAUDE.md                  # Working rules for the AI assistant on this repo
│
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, lifespan (settings check), CORS, error handlers
│   │   ├── security.py        # Settings validation, bcrypt hashing, PyJWT encode/decode
│   │   ├── rate_limit.py      # slowapi limiter and limits
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   ├── database.py        # Engine and session factory
│   │   ├── permissions.py     # Permission names and what each role grants
│   │   ├── cli.py             # python -m app.cli create-admin | promote | verify-email | ...
│   │   ├── routers/           # auth, credentials, admin, profile
│   │   ├── services/          # Auth, Encryptor, Audit, RefreshToken, email services
│   │   ├── middleware/        # require_permission / require_admin / get_current_claims
│   │   └── utils/             # audit_columns helpers, email validator
│   ├── migrations/            # Alembic migrations — the schema's source of truth
│   ├── alembic.ini
│   ├── db/
│   │   ├── schema.sql         # PostgreSQL DDL generated from the migrations
│   │   └── generate_schema_sql.py
│   ├── tests/                 # pytest: unit, Hypothesis properties, integration, contract, migrations
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── pages/             # Login, SignUp, ViewSearch, SaveCredential, EditCredential, AdminUsers, VerifyEmail, Forbidden
│   │   ├── components/        # AppLayout, SessionBootstrap, ProtectedRoute, PasswordInput, modals, LanguageToggle
│   │   ├── hooks/             # useVisibilityTimer
│   │   ├── context/           # AuthContext (access token in memory only)
│   │   ├── api/               # apiClient (axios, bearer token, silent refresh)
│   │   ├── i18n/              # en.json, es.json, i18n.ts
│   │   └── router.tsx         # React Router v7 routes
│   ├── e2e/                   # Playwright end-to-end tests
│   ├── playwright.config.ts
│   ├── package.json
│   └── Dockerfile
│
└── .kiro/specs/               # Specification: requirements, design, tasks
```

---

## Application Screens

### Login (`/login`)

The entry point. Enter username and password to authenticate. On success, a JWT is stored in React memory (not `localStorage`) and the user is taken to Home. Expired tokens redirect back here automatically.

When enabled: an hCaptcha challenge must be solved before logging in, and an account whose email is not verified gets a reminder (with **Resend email**) after logging in. Unverified accounts are deactivated 30 days after sign-up; an administrator reactivates them with `python -m app.cli verify-email --username <name>`.

### Sign Up (`/signup`)

Create a new account. Password must be at least 12 characters and include at least one uppercase letter, one lowercase letter, one digit, and one symbol (`@`, `$`, or `!`). Password confirmation must match exactly.

### Verify Email (`/verify-email?token=…`)

Opened from the verification email. Each link works once and expires after 48 hours; log in to request a new one.

### Moving around

A side menu groups the screens: **Home**, **Vault** (My Credentials, Save Credential) and **Administration** (Admin only). Click a group title to close or open it; the menu remembers it on that device. The arrow at the top folds the menu to icons (the names appear on hover). On a phone the ☰ button opens the menu, which closes after choosing a screen. Your name at the top right opens the account menu with your role and **Log Out**.

### Home (`/`)

The first screen after logging in: how many credentials you have (and how many sign in with an email or a username) and the five you changed most recently.

### View / Search Credentials (`/credentials`)

The main screen. The search box filters as you type by website name or email/username, ignoring upper/lower case and accents (`jose` finds `José`). Filter by sign-in type (email or username), page through the results (`1–10 of 42`, 10 to 100 per page) and switch between a table and cards; the table/cards choice is saved in your account. Results appear in a table with these columns:

| Column | Notes |
|--------|-------|
| Website | Name of the site |
| Email / Username | Login identifier |
| Password | Always masked by default |
| 👁 Eye icon | Reveals the password for that row |
| ✏️ Edit icon | Opens the edit page |
| 🗑 Delete icon | Starts the delete flow |

**Revealing a password:**
1. Click the eye icon.
2. Enter your account password in the confirmation prompt.
3. The plaintext password appears. A 60-second countdown starts.
4. The password is masked automatically when the timer reaches zero, or immediately if you click the eye again.
5. If another password is already visible, a warning asks you to confirm before proceeding.

### Save Credential (`/credentials/new`)

Form to store a new credential. Fields: website name, email (or username if "Username Login" is checked), and password. Required fields carry a red asterisk and the ⓘ next to a label explains the field; if something is missing or wrong, the field turns red, gets the focus and the reason appears under it. The password field has an eye toggle for review before saving. Submitting shows the account-password confirmation prompt.

### Edit Credential (`/credentials/:id/edit`)

Pre-populated form with the existing credential data. The password field is masked initially. Change any field and click Update — the account-password prompt appears before the change is saved. Cancel returns to the search screen without saving.

### Admin — Users (`/admin/users`) *(Admin only)*

Lists all registered users with their role (User or Admin) and whether their email is verified, with search by name or email, filters by role and verification, pages and table/cards view. A dropdown per row changes another user's role; your own row is locked so there is always an Admin. The Admin never sees other users' passwords.

### 403 Forbidden (`/403`)

Shown when someone opens a screen their role does not allow (for example a User opening the user administration).

---

## Language Toggle

A control in the application header switches between **English** (default) and **Español**. The switch takes effect immediately, with no page reload. The selection persists for the current browser session.

---

## Security Notes

- Saved passwords are encrypted with **Fernet (AES-128-CBC + HMAC-SHA256)** on the server before they reach the database. The key (`FERNET_KEY`) never leaves the server.
- Your account password is stored only as a **bcrypt hash**.
- Revealing, saving, editing or deleting a credential always asks for your **account password again**.
- Each user can only ever see and change **their own** credentials.
- A login lasts up to 8 hours. The short-lived access token is kept only in the page's memory; the session itself is renewed through a cookie that page scripts cannot read. **Log Out** ends the session on the server too.
- Repeated failed logins or wrong account passwords are **slowed down** (HTTP 429 after a few attempts per minute).
- Every save, reveal, edit and delete is recorded in an **audit log**.
- The server refuses to start without strong secrets.
- Optional: hCaptcha on the login page and email verification (reminders 7 and 1 days before; accounts not verified within 30 days are deactivated).
- In production the database is backed up daily; restoring a backup is a single command.
- In production all traffic is HTTPS (HTTP redirects to HTTPS, HSTS enabled), and the application's database account cannot change or drop tables.

Technical details: [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Makefile Reference

| Command | Description |
|---------|-------------|
| `make up` | Build images and start all services in the background |
| `make down` | Stop and remove containers |
| `make test-backend` | Run the full backend pytest suite |
| `make test-frontend` | Run the frontend Vitest suite |
| `make test-e2e` | Run the Playwright end-to-end tests |
| `make lint` | ruff + eslint |
| `make smoke-prod` | Build and smoke-test the production stack locally (Docker) |
| `make backup` | Take a production backup now |
| `make create-admin USERNAME=.. EMAIL=..` | Create an Admin account (Docker) |
| `make install-backend` | Install Python dependencies locally (no Docker) |
| `make install-frontend` | Install Node.js dependencies locally (no Docker) |
| `make help` | List all available commands |

---

## Project Status

All tasks from the Kiro plan (1–29) and the follow-up phases (30–34) are done; CI is green on every push. Details and history: [`tasks.md`](.kiro/specs/password-manager-website/tasks.md).

**Fixed since the Kiro handover (2026-11-12)**

| Area | Problem found | Fix |
|---|---|---|
| Login | Every login bounced back to `/login` (JWT lacked `username`) | Claim added (30.1) |
| Permissions | Missing `/api/profile/permissions`, `/api/credentials/{id}`, `/api/admin/profiles`; new users had no profile; no way to create an Admin | Endpoints, seeded profiles, `create-admin` CLI (30.2–30.5) |
| Sessions | A wrong account password logged the user out; reload lost the session | Interceptor fix; httpOnly refresh cookie with rotation (30.6, 31.5) |
| UI | No language toggle, navigation or logout | `AppLayout` header (30.7) |
| Build and tests | 33 TypeScript errors broke `npm run build`; 7 backend tests failing; one flaky property test | Fixed (30.0, 30.8, 32.9) |
| Security | Weak-secret fallback, unmaintained JWT/hash libraries, no rate limits, ~40 vulnerable Python packages, react-router advisory | Fail-fast settings, PyJWT + bcrypt, slowapi + Redis, upgrades (31.x, 32.8, 34.1) |
| Data | Audit date (local) and time (UTC) could disagree; searching `%` matched everything; schema built with `create_all` | One UTC instant, escaped LIKE + trigram indexes, Alembic migrations (32.3, 32.4, 31.6) |
| Deployment | `.env.prod` not git-ignored; health check pointed to a missing endpoint; CI broke on Ubuntu 26 | Ignored, `/api/health` added, runners pinned (32.6, 32.2) |
| Spec Phase 2 | Email verification, deactivation and CAPTCHA not implemented | Done, with reminders (33, 34.4) |
| Operations | No backups; rate limits per process | Daily backups + restore script; Redis (34.2, 34.3) |
| Permissions | Per-user screen profiles, an Admin that bypassed every check | One role per account with per-action permissions, no bypass, role read on every request (37.1) |
| Local use | Dev database clashed with the native PostgreSQL on 5432; no way to run it permanently on the laptop | Dev ports only on 127.0.0.1 (DB 5436); local installation with IIS, backups and per-device limits (36) |

**Pending** (tasks 35–37)

- Local installation on this laptop: installed on 2026-11-15 (task 36); the phone test is left.
- Task 37 (decided 2026-11-15): bring Savings Tool's screens and settings — side menu and interface patterns, appearance and personal settings, user administration and audit view, mandatory 2FA and session limits, in-app help. 37.1 (roles and permissions) and 37.2 (menu, Home, lists and form patterns) are done.
- Monitoring and alerts. (A real server and cloud backups were dropped in favour of the local installation.)
- GitHub Actions on Node 24.
- Password reset, two-factor authentication, password generator, export and account deletion — outside the original spec.
- Decide whether to move to client-side (zero-knowledge) encryption before real users.

---

## Documentation

- [`requirements.md`](.kiro/specs/password-manager-website/requirements.md) — Functional and non-functional requirements in EARS notation.
- [`design.md`](.kiro/specs/password-manager-website/design.md) — Architecture, component design, data models, API shapes, security considerations, and correctness properties.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Technical deep-dive: components, encryption lifecycle, authentication and session refresh, permission model, schema and migrations, Fernet key rotation, audit log.
- [`tasks.md`](.kiro/specs/password-manager-website/tasks.md) — Implementation plan and status (tasks 1–29 from Kiro, 30–34 done afterwards, 35 = backlog, 36 = local installation).
- [`docs/local-install.md`](docs/local-install.md) — Local installation on Windows: pieces, ports, install, update, tools, restore.
