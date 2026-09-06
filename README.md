# Save-Pass — Password Manager

A full-stack secure password manager web application. Users can store, search, reveal, edit, and delete credentials for any website. All encryption happens exclusively on the backend — the frontend never sees an encryption key or a plaintext password from the database.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript, Vite, Tailwind CSS, react-i18next |
| Backend | Python 3.11, FastAPI, SQLAlchemy ORM |
| Database | PostgreSQL 15 |
| Auth | JWT (HS256, 15-minute expiry) |
| Encryption | Fernet / AES-128-CBC (`cryptography` library) |
| Password hashing | bcrypt (`passlib`) |
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
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
make install-frontend      # npm install inside frontend/
cd frontend
npm run dev
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

Covers: `PasswordInput` Eye_Toggle, `PasswordConfirmModal` callbacks, `useVisibilityTimer` with fake timers, `ProtectedRoute` redirects, `LanguageToggle` language switching.

---

## Project Structure

```
save-pass/
├── .env.example               # Environment variable template
├── docker-compose.yml         # Orchestrates db, backend, frontend
├── Makefile                   # Common dev commands
│
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, CORS, exception handlers
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   ├── database.py        # Engine and session factory
│   │   ├── routers/           # auth_router, credentials_router, admin_router
│   │   ├── services/          # AuthService, EncryptorService, ProfileService, AuditService
│   │   ├── middleware/        # require_permission dependency
│   │   └── utils/             # audit_columns helpers
│   ├── db/
│   │   └── schema.sql         # Full PostgreSQL DDL
│   ├── tests/                 # pytest test suite
│   ├── requirements.txt
│   ├── pytest.ini
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── pages/             # LoginPage, SignUpPage, ViewSearchPage, SaveCredentialPage, EditCredentialPage, AdminUsersPage, AdminProfilesPage, ForbiddenPage
│   │   ├── components/        # PasswordInput, PasswordConfirmModal, ConfirmDeleteModal, AlreadyVisibleModal, ProtectedRoute, LanguageToggle
│   │   ├── hooks/             # useVisibilityTimer
│   │   ├── context/           # AuthContext (token in memory, not localStorage)
│   │   ├── api/               # apiClient (axios + JWT interceptor)
│   │   ├── i18n/              # en.json, es.json, i18n.ts
│   │   └── router.tsx         # React Router v6 route definitions
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
│
└── .kiro/specs/               # Full feature specification (requirements, design, tasks)
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

- All credential passwords are encrypted with **Fernet (AES-128-CBC + HMAC-SHA256)** before reaching the database.
- The Fernet key lives exclusively in the server environment (`FERNET_KEY`). It is never sent to the frontend or written to logs.
- Account passwords are stored as **bcrypt hashes** only. Plaintext account passwords are never persisted.
- JWTs are kept in **React in-memory state**, not `localStorage` or cookies, to reduce XSS exposure.
- Every mutation (save, edit, delete) and every password reveal requires the user to **re-enter their account password** — there is no session-level bypass.
- Every credential query uses `WHERE user_id = <authenticated_user_id>`, enforcing strict **per-user data isolation**.
- All database operations use **SQLAlchemy ORM parameterized queries** — no raw SQL string interpolation.

---

## Makefile Reference

| Command | Description |
|---------|-------------|
| `make up` | Build images and start all services in the background |
| `make down` | Stop and remove containers |
| `make test-backend` | Run the full backend pytest suite |
| `make test-frontend` | Run the frontend Vitest suite |
| `make install-backend` | Install Python dependencies locally (no Docker) |
| `make install-frontend` | Install Node.js dependencies locally (no Docker) |
| `make help` | List all available commands |

---

## Documentation

- [`requirements.md`](.kiro/specs/password-manager-website/requirements.md) — Functional and non-functional requirements in EARS notation.
- [`design.md`](.kiro/specs/password-manager-website/design.md) — Architecture, component design, data models, API shapes, security considerations, and correctness properties.
- `ARCHITECTURE.md` — *(coming in task 28.2)* Technical deep-dive: encryption lifecycle, auth flow, schema overview, Fernet key rotation, audit log structure.
