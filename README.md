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
- **Role-based access control** — two roles (User, Admin) with a profile/permissions system. Admins control which screens each user can access.
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
DATABASE_URL=postgresql://savepass_user:savepass_password@localhost:5432/savepass
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

On startup the backend seeds two permission profiles: **Basic** (view/search only) and **Full** (view, save, edit, delete). Every new sign-up gets **Full** by default (change with the `DEFAULT_PROFILE` env var).

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
| `FERNET_KEY` | 32-byte URL-safe base64 key for credential encryption | _(generated)_ |
| `JWT_SECRET` | Secret used to sign and verify JWTs | _(random string)_ |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `JWT_EXPIRE_MINUTES` | Token lifetime in minutes | `15` |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins | `http://localhost:5173` |
| `DEFAULT_PROFILE` | Profile assigned to every new sign-up (empty = none) | `Full` |
| `REFRESH_EXPIRE_HOURS` | How long a login lasts without re-entering the password | `8` |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | Refresh cookie flags | `true` / `strict` |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_STORAGE` | Rate limiting on/off and its store (use Redis with several workers) | `true` / `memory://` |

The backend **refuses to start** if `JWT_SECRET` is missing or shorter than 32 characters, or if `FERNET_KEY` is not a valid Fernet key. Generate a JWT secret with:

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

### Backend (pytest + Hypothesis property tests)

```bash
make test-backend
# equivalent to: cd backend && python -m pytest tests/ -v
```

The backend test suite includes:
- Unit tests for `AuthService`, `EncryptorService`, `ProfileService`, and `AuditService`.
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

Playwright starts its own backend (port 8001, throwaway SQLite database) and frontend (port 5174), then drives a real browser through sign-up, login, save, search, reveal, edit, delete, language switch, logout and the admin profile assignment. No mocks and no Docker required.

---

## Project Structure

```
save-pass/
├── .env.example               # Environment variable template
├── docker-compose.yml         # Orchestrates db, backend, frontend
├── Makefile                   # Common dev commands
├── ARCHITECTURE.md            # Technical deep-dive (flows, schema, key rotation)
├── CLAUDE.md                  # Working rules for the AI assistant on this repo
│
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, lifespan (settings check + seed), CORS, error handlers
│   │   ├── security.py        # Settings validation, bcrypt hashing, PyJWT encode/decode
│   │   ├── rate_limit.py      # slowapi limiter and limits
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   ├── database.py        # Engine and session factory
│   │   ├── seed.py            # Default profiles (Basic, Full) + default profile on sign-up
│   │   ├── cli.py             # python -m app.cli seed | create-admin | promote
│   │   ├── routers/           # auth, credentials, admin, profile
│   │   ├── services/          # Auth, Encryptor, Profile, Audit, RefreshToken services
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
│   │   ├── pages/             # Login, SignUp, ViewSearch, SaveCredential, EditCredential, AdminUsers, AdminProfiles, Forbidden
│   │   ├── components/        # AppLayout, SessionBootstrap, ProtectedRoute, PasswordInput, modals, LanguageToggle
│   │   ├── hooks/             # useVisibilityTimer
│   │   ├── context/           # AuthContext (access token in memory only)
│   │   ├── api/               # apiClient (axios, bearer token, silent refresh)
│   │   ├── i18n/              # en.json, es.json, i18n.ts
│   │   └── router.tsx         # React Router v6 routes
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

The entry point. Enter username and password to authenticate. On success, a JWT is stored in React memory (not `localStorage`) and the user is redirected to the credentials screen. Expired tokens redirect back here automatically.

### Sign Up (`/signup`)

Create a new account. Password must be at least 12 characters and include at least one uppercase letter, one lowercase letter, one digit, and one symbol (`@`, `$`, or `!`). Password confirmation must match exactly.

### View / Search Credentials (`/credentials`)

The main screen. A search box filters credentials in real time by website name or email/username (case-insensitive). Results appear in a table with these columns:

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

Form to store a new credential. Fields: website name, email (or username if "Username Login" is checked), and password. The password field has an eye toggle for review before saving. Submitting shows the account-password confirmation prompt.

### Edit Credential (`/credentials/:id/edit`)

Pre-populated form with the existing credential data. The password field is masked initially. Change any field and click Update — the account-password prompt appears before the change is saved. Cancel returns to the search screen without saving.

### Admin — Users (`/admin/users`) *(Admin only)*

Lists all registered users with their currently assigned profile. Provides a dropdown per row to reassign profiles.

### Admin — Profiles (`/admin/profiles`) *(Admin only)*

Displays all available profiles and the screens each one permits.

### 403 Forbidden (`/403`)

Shown when a User attempts to access a screen not covered by their profile.

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
| `make seed` | Seed default profiles (Docker) |
| `make create-admin USERNAME=.. EMAIL=..` | Create an Admin account (Docker) |
| `make install-backend` | Install Python dependencies locally (no Docker) |
| `make install-frontend` | Install Node.js dependencies locally (no Docker) |
| `make help` | List all available commands |

---

## Documentation

- [`requirements.md`](.kiro/specs/password-manager-website/requirements.md) — Functional and non-functional requirements in EARS notation.
- [`design.md`](.kiro/specs/password-manager-website/design.md) — Architecture, component design, data models, API shapes, security considerations, and correctness properties.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — Technical deep-dive: components, encryption lifecycle, authentication and session refresh, permission model, schema and migrations, Fernet key rotation, audit log.
- [`tasks.md`](.kiro/specs/password-manager-website/tasks.md) — Implementation plan and status (tasks 1–29 from Kiro, 30+ added afterwards).
