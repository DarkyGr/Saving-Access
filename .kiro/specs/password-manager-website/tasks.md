# Implementation Plan: Password Manager Website

## Overview

Full-stack implementation of a secure password manager using FastAPI (Python) on the backend and React + TypeScript (Vite) on the frontend. Tasks are organized incrementally — infrastructure and data layer first, then backend services, then API routers, then frontend pages, then tests. Every task builds on the previous ones and all code is wired together by the final integration step.

## Tasks

- [x] 1. Project scaffolding and monorepo structure
  - Create root-level `docker-compose.yml` with services: `db` (postgres:15), `backend` (FastAPI), `frontend` (Vite dev server)
  - Create `.env.example` with all required env vars: `DATABASE_URL`, `FERNET_KEY`, `JWT_SECRET`, `JWT_ALGORITHM=HS256`, `JWT_EXPIRE_MINUTES=15`, `CORS_ORIGINS`
  - Create `backend/` directory with `pyproject.toml` (or `requirements.txt`) pinning: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg2-binary`, `cryptography`, `passlib[bcrypt]`, `python-jose[cryptography]`, `python-dotenv`, `hypothesis`, `pytest`, `pytest-asyncio`, `httpx`
  - Create `frontend/` directory bootstrapped with `npm create vite@latest` using the `react-ts` template; install `react-router-dom`, `react-i18next`, `i18next`, `axios`, `tailwindcss`, `postcss`, `autoprefixer`; initialize Tailwind config
  - Create root-level `Makefile` or `justfile` with targets: `up`, `down`, `test-backend`, `test-frontend`
  - _Requirements: 8.4, 9.9_


- [x] 2. Database schema DDL script
  - [x] 2.1 Write `backend/db/schema.sql` with all five CREATE TABLE statements (`users`, `profiles`, `user_profiles`, `credentials`, `audit_log`) including audit columns, CHECK constraints, and FK references exactly as specified in the design
  - [x] 2.2 Add all six indexes (`idx_credentials_user_id`, `idx_credentials_website_name`, `idx_credentials_email_username`, `idx_audit_log_user_id`) and the `app_user` role with minimal GRANT statements to `schema.sql`
  - _Requirements: 9.1–9.9_

- [x] 3. SQLAlchemy ORM models
  - [x] 3.1 Create `backend/app/models.py` defining `Base = declarative_base()` and mapped classes `User`, `Profile`, `UserProfile`, `Credential`, `AuditLog` matching every column and relationship in the ERD; include `__table_args__` for indexes
  - [x] 3.2 Create `backend/app/database.py` with `engine`, `SessionLocal`, and `get_db` dependency function reading `DATABASE_URL` from env
  - _Requirements: 9.1–9.8, 8.6_

- [x] 4. Backend application setup (FastAPI entry point, CORS, exception handlers)
  - Create `backend/app/main.py` instantiating `FastAPI()`, registering `CORSMiddleware` with `CORS_ORIGINS` from env, and global exception handlers for `401`, `403`, `404`, `422`, and `500` returning the standard JSON shapes defined in the design
  - Include `@app.on_event("startup")` that runs `Base.metadata.create_all(bind=engine)` in non-production environments
  - _Requirements: 8.4, 8.6_

- [x] 5. EncryptorService
  - [x] 5.1 Create `backend/app/services/encryptor_service.py` implementing `EncryptorService` with `encrypt(plaintext: str) -> bytes` using `Fernet(FERNET_KEY)` and `decrypt(ciphertext: bytes) -> str`; load key from env var at instantiation; raise `ValueError` if key is absent
  - [x] 5.2 Write property test for credential encryption invariant (Property 9)
    - **Property 9: Credential Encryption Invariant** — `encrypt(p)` result is a valid Fernet token that decrypts to `p` and never equals `p`
    - **Validates: Requirements 4.10, 6.7, 8.1**
    - Minimum 200 Hypothesis iterations; use `st.text(min_size=1)` strategy
  - _Requirements: 8.1, 8.2, 8.3_


- [x] 6. AuthService
  - [x] 6.1 Create `backend/app/services/auth_service.py` implementing `AuthService` with:
    - `register(payload) -> User`: validates password strength (length ≥ 12, uppercase, lowercase, digit, symbol from `@$!`), validates password_confirmation match, checks duplicate username/email, hashes password with `passlib.hash.bcrypt` (rounds=12), sets audit columns, commits to DB
    - `login(payload) -> dict`: looks up user by username, verifies bcrypt hash, on success issues HS256 JWT with `user_id`, `role`, `exp=now+15min`; on any failure returns the same generic error
    - `verify_token(token: str) -> dict`: decodes and validates JWT; raises `401` on expiry or invalid signature
    - `check_account_password(user_id: int, raw: str) -> bool`: fetches `password_hash`, runs `bcrypt.verify`
  - [x] 6.2 Write property test for password confirmation match (Property 1)
    - **Property 1: Password Confirmation Match** — register accepts iff `password == password_confirmation`
    - **Validates: Requirements 1.3, 1.4**
    - Minimum 100 Hypothesis iterations
  - [x] 6.3 Write property test for password strength validation (Property 2)
    - **Property 2: Password Strength Validation** — validator rejects iff at least one rule (length, uppercase, lowercase, digit, symbol) is unmet
    - **Validates: Requirements 1.5, 1.6**
    - Minimum 200 Hypothesis iterations; generate strings with `st.text()`
  - [x] 6.4 Write property test for account password hashing (Property 3)
    - **Property 3: Account Password Hashing** — stored `password_hash` is a valid bcrypt hash and differs from plaintext
    - **Validates: Requirements 1.7, 8.5**
    - Minimum 100 Hypothesis iterations
  - [x] 6.5 Write property test for JWT issued on successful login (Property 6)
    - **Property 6: JWT Issued on Successful Login** — response contains `access_token` with `user_id`, `role`, and `exp` within 15 min
    - **Validates: Requirements 2.4**
    - Minimum 100 Hypothesis iterations
  - [x] 6.6 Write property test for generic error on invalid login (Property 5)
    - **Property 5: Generic Error on Invalid Login** — all failed login attempts return the same generic response body
    - **Validates: Requirements 2.3**
    - Minimum 100 Hypothesis iterations
  - _Requirements: 1.3–1.7, 2.2–2.4, 8.5_


- [x] 7. AuditService and audit column helpers
  - [x] 7.1 Create `backend/app/services/audit_service.py` implementing `AuditService.log(user_id, operation, affected_record_id)` that writes a row to `audit_log` and commits synchronously; `operation` must be one of `SELECT|INSERT|UPDATE|DELETE`
  - [x] 7.2 Create `backend/app/utils/audit_columns.py` with `set_creation_audit(record, user_id)` and `set_modification_audit(record, user_id)` helper functions that populate the six audit column fields with `date.today()` and `datetime.utcnow().time()`
  - [x] 7.3 Write property test for audit columns on creation (Property 4)
    - **Property 4: Audit Columns on Creation** — `creation_date`, `creation_time`, `creation_user_id` are all non-null after any record creation
    - **Validates: Requirements 1.8, 4.11, 9.8**
    - Minimum 100 Hypothesis iterations using mocked DB session
  - [x] 7.4 Write property test for audit log entry on every mutation and reveal (Property 13)
    - **Property 13: Audit Log Entry on Every Mutation and Reveal** — after each INSERT/SELECT/UPDATE/DELETE operation an `audit_log` row exists with correct `operation`, `user_id`, and `affected_record_id`
    - **Validates: Requirements 4.12, 5.14, 6.9, 7.7**
    - Minimum 100 Hypothesis iterations
  - _Requirements: 1.8, 4.11, 4.12, 5.14, 6.8, 6.9, 7.7, 9.5, 9.8_

- [x] 8. ProfileService
  - [x] 8.1 Create `backend/app/services/profile_service.py` implementing:
    - `get_user_permissions(user_id: int) -> list[str]`: queries `user_profiles` → `profiles.permitted_screens`; returns `["*"]` for Admin role
    - `assign_profile(admin_id: int, user_id: int, profile_id: int)`: updates or inserts `user_profiles` row, calls `set_modification_audit`, commits
  - [x] 8.2 Write property test for non-admin denied access to admin endpoints (Property 7)
    - **Property 7: Non-Admin Denied Access to Admin Screens** — any JWT with `role="User"` receives HTTP 403 on all `/api/admin/*` endpoints
    - **Validates: Requirements 3.2, 3.4, 3.6**
    - Minimum 100 Hypothesis iterations using `httpx` TestClient
  - [x] 8.3 Write property test for profile assignment updates audit columns (Property 8)
    - **Property 8: Profile Assignment Updates Audit Columns** — after `assign_profile`, `modification_date`, `modification_time`, `modification_user_id` are non-null and equal current timestamp and admin's user_id
    - **Validates: Requirements 3.3**
    - Minimum 100 Hypothesis iterations using mocked DB
  - _Requirements: 3.1–3.7_


- [x] 9. Permission middleware
  - Create `backend/app/middleware/permissions.py` with a `require_permission(screen: str)` FastAPI dependency factory: decodes JWT from `Authorization: Bearer`, checks `role == "Admin"` → pass; else fetches `ProfileService.get_user_permissions(user_id)` and checks `screen in permissions`; raises `HTTPException(403)` on failure
  - _Requirements: 3.2, 3.4, 3.5, 3.6_

- [x] 10. Auth router
  - Create `backend/app/routers/auth_router.py` with:
    - `POST /api/auth/register` → calls `AuthService.register`; returns 201 `{user_id, username, role}`
    - `POST /api/auth/login` → calls `AuthService.login`; returns 200 `{access_token, token_type, expires_in}`
  - Wire router into `main.py` with `app.include_router(auth_router, prefix="/api/auth")`
  - _Requirements: 1.1–1.8, 2.1–2.4_

- [x] 11. Credentials router
  - [x] 11.1 Create `backend/app/routers/credentials_router.py` with:
    - `GET /api/credentials?q=` — requires `require_permission("credentials")`; queries DB with `WHERE user_id=? AND (website_name ILIKE %q% OR email_or_username ILIKE %q%)` using parameterized ORM filter; returns list with `password: null`
    - `POST /api/credentials` — requires `require_permission("credentials.new")`; calls `check_account_password`; calls `EncryptorService.encrypt`; sets audit columns; commits; logs INSERT to `AuditService`; returns 201
    - `PUT /api/credentials/{id}` — requires `require_permission("credentials.edit")`; verifies ownership (`user_id`); calls `check_account_password`; re-encrypts; sets modification audit columns; commits; logs UPDATE; returns 200
    - `DELETE /api/credentials/{id}` — requires `require_permission("credentials.delete")`; verifies ownership; calls `check_account_password`; hard-deletes; logs DELETE; returns 204
    - `POST /api/credentials/{id}/reveal` — requires `require_permission("credentials")`; verifies ownership; calls `check_account_password`; calls `EncryptorService.decrypt`; logs SELECT; returns `{password: plaintext}`
  - [x] 11.2 Wire credentials router into `main.py`
  - [x] 11.3 Write property test for credential ownership isolation (Property 10)
    - **Property 10: Credential Ownership Isolation** — user U cannot list, reveal, edit, or delete any credential owned by user V
    - **Validates: Requirements 5.3, 8.2**
    - Minimum 100 Hypothesis iterations
  - [x] 11.4 Write property test for search filter correctness (Property 11)
    - **Property 11: Search Filter Correctness** — every returned credential contains query Q as case-insensitive substring in `website_name` or `email_or_username`
    - **Validates: Requirements 5.2**
    - Minimum 200 Hypothesis iterations
  - [x] 11.5 Write property test for wrong account password rejects sensitive operations (Property 14)
    - **Property 14: Wrong Account Password Rejects Sensitive Operations** — any save/reveal/edit/delete with incorrect account password returns 401 and performs no mutation
    - **Validates: Requirements 4.9, 6.6, 7.5**
    - Minimum 100 Hypothesis iterations
  - _Requirements: 4.1–4.13, 5.1–5.14, 6.1–6.9, 7.1–7.7, 8.1–8.3_


- [x] 12. Admin router
  - Create `backend/app/routers/admin_router.py` with:
    - `GET /api/admin/users` — requires `require_permission("admin.users")` (Admin only); returns list of all users with their assigned profile
    - `PUT /api/admin/users/{user_id}/profile` — requires Admin; calls `ProfileService.assign_profile`; returns `{user_id, profile_id}`
  - Wire admin router into `main.py`
  - _Requirements: 3.2, 3.3, 3.5, 3.7_

- [x] 13. Email validation utility
  - Create `backend/app/utils/email_validator.py` with `validate_email(email: str) -> bool` that checks RFC 5321 format using a regex and rejects domains from a bundled `disposable_domains.txt` blocklist file; integrate into `AuthService.register` and the credentials router email field
  - [x] 13.1 Write property test for email validation (Property 16)
    - **Property 16: Email Validation Rejects Invalid Formats and Disposable Domains** — validator accepts iff RFC 5321 format is valid AND domain is not on blocklist
    - **Validates: Requirements 4.13**
    - Minimum 200 Hypothesis iterations using `st.emails()` and manually constructed invalid strings
  - _Requirements: 4.13_

- [x] 14. Backend checkpoint — ensure all backend tests pass
  - Run `pytest backend/` and confirm all unit and property-based tests pass with zero failures; fix any issues before proceeding to frontend tasks.


- [x] 15. Frontend i18n setup and translation files
  - [x] 15.1 Create `frontend/src/i18n/i18n.ts` initializing `i18next` with `react-i18next`, language detection from browser, fallback to `"en"`, and `sessionStorage` persistence
  - [x] 15.2 Create `frontend/src/i18n/en.json` with all English string keys covering: login, signup, navigation, credential form labels, modal text, error messages, table headers, admin page labels, password rules, and timer text
  - [x] 15.3 Create `frontend/src/i18n/es.json` with equivalent Spanish translations for every key in `en.json`
  - Import and initialize i18n in `frontend/src/main.tsx`
  - _Requirements: 10.1–10.5_

- [x] 16. Frontend shared components
  - [x] 16.1 Create `frontend/src/components/PasswordInput.tsx` — masked text input with an Eye_Toggle `<button>` that toggles `type="password"` / `type="text"`; uses `t()` for aria-label; min touch target 44×44 px on mobile
  - [x] 16.2 Create `frontend/src/components/PasswordConfirmModal.tsx` — modal dialog with a `PasswordInput` and confirm/cancel buttons; accepts `onConfirm(password: string)` and `onCancel()` callbacks; uses `t()` for all text
  - [x] 16.3 Create `frontend/src/hooks/useVisibilityTimer.ts` — custom hook that accepts `durationMs=60000`, returns `{isVisible, startTimer, stopTimer, secondsRemaining}`; uses `useRef` for interval ID to avoid stale closure issues
  - [x] 16.4 Create `frontend/src/components/LanguageToggle.tsx` — button group or dropdown in the app header that calls `i18n.changeLanguage("en" | "es")`; persists choice to `sessionStorage`
  - [x] 16.5 Create `frontend/src/components/ProtectedRoute.tsx` — HOC that reads JWT from memory context, decodes claims; Admin passes unconditionally; User role calls `GET /api/profile/permissions` and checks screen key; redirects to `/login` if unauthenticated or `/403` if forbidden
  - [x] 16.6 Create `frontend/src/components/ConfirmDeleteModal.tsx` — generic confirmation modal with cancel and confirm buttons and i18n text
  - [x] 16.7 Create `frontend/src/components/AlreadyVisibleModal.tsx` — warning modal for the "another password is visible" state; "Continue" callback hides current and proceeds; "Cancel" closes modal
  - _Requirements: 4.5–4.7, 5.4–5.12, 7.2–7.3, 10.1–10.4, 11.2_


- [x] 17. Frontend API client and auth context
  - [x] 17.1 Create `frontend/src/api/apiClient.ts` using `axios` with a base URL from `import.meta.env.VITE_API_URL`; add a request interceptor that injects `Authorization: Bearer <token>` from React memory; add a response interceptor that redirects to `/login` on 401
  - [x] 17.2 Create `frontend/src/context/AuthContext.tsx` with `AuthProvider` holding `token` and `user` in `useState` (never `localStorage`); expose `login(token)`, `logout()`, and `useAuth()` hook
  - _Requirements: 2.2, 2.4, 2.5, 8.3_

- [x] 18. LoginPage
  - Create `frontend/src/pages/LoginPage.tsx` with username and password fields (using `PasswordInput`), form validation, calls `POST /api/auth/login`, stores token via `AuthContext.login()`, redirects to `/credentials` on success, displays generic error message on 401; all text via `t()`
  - _Requirements: 2.1–2.5_

- [x] 19. SignUpPage
  - Create `frontend/src/pages/SignUpPage.tsx` with username, email, password, and password_confirmation fields; client-side password strength validation displaying per-rule errors via `t()`; calls `POST /api/auth/register`; on 201 redirects to `/login`; all text via `t()`
  - _Requirements: 1.1–1.8_

- [x] 20. SaveCredentialPage
  - Create `frontend/src/pages/SaveCredentialPage.tsx` with `website_name`, email/username toggle (controlled by `is_username_login` checkbox), `PasswordInput` for credential password, Eye_Toggle; on submit shows `PasswordConfirmModal`; on confirm calls `POST /api/credentials` with `account_password`; redirects to `/credentials` on 201; all text via `t()`
  - _Requirements: 4.1–4.13_

- [x] 21. ViewSearchPage
  - [x] 21.1 Create `frontend/src/pages/ViewSearchPage.tsx` with a search input that calls `GET /api/credentials?q=` on change (debounced 300 ms); renders results in a responsive table (horizontally scrollable on mobile) with columns: website, email/username, password (masked), eye icon, edit icon, delete icon
  - [x] 21.2 Implement Eye_Toggle logic in `ViewSearchPage`: clicking eye checks `AlreadyVisibleModal` if another row is visible; shows `PasswordConfirmModal`; on confirm calls `POST /api/credentials/{id}/reveal`; displays plaintext; starts `useVisibilityTimer` for 60 s; auto-masks on timer expiry; manual click on open eye masks immediately
  - [x] 21.3 Implement Delete flow in `ViewSearchPage`: delete icon opens `ConfirmDeleteModal`; on confirm shows `PasswordConfirmModal`; on confirm calls `DELETE /api/credentials/{id}` with `account_password`; refreshes list
  - [x] 21.4 Add edit icon link in each row navigating to `/credentials/:id/edit`
  - _Requirements: 5.1–5.14, 7.1–7.7_


- [x] 22. EditCredentialPage
  - Create `frontend/src/pages/EditCredentialPage.tsx` that fetches credential by `GET /api/credentials/:id` (no reveal), pre-populates `website_name`, email/username, and masked password; on "Update" shows `PasswordConfirmModal`; on confirm calls `PUT /api/credentials/:id` with `account_password`; on success redirects to `/credentials`; includes "Cancel" button; all text via `t()`
  - _Requirements: 6.1–6.9_

- [x] 23. AdminUsersPage and AdminProfilesPage
  - [x] 23.1 Create `frontend/src/pages/AdminUsersPage.tsx` that calls `GET /api/admin/users`; renders a table of users with their current profile; includes a dropdown per row to reassign profile via `PUT /api/admin/users/{id}/profile`; all text via `t()`
  - [x] 23.2 Create `frontend/src/pages/AdminProfilesPage.tsx` that reads available profiles (seed data) and displays their `permitted_screens` for reference; Admin-only route
  - _Requirements: 3.2, 3.3, 3.5, 3.7_

- [x] 24. React Router setup and 403 page
  - [x] 24.1 Create `frontend/src/router.tsx` using `react-router-dom v6` `createBrowserRouter` with all routes: `/login` → `LoginPage`, `/signup` → `SignUpPage`, `/credentials` → `ProtectedRoute(screen="credentials")` → `ViewSearchPage`, `/credentials/new` → `ProtectedRoute(screen="credentials.new")` → `SaveCredentialPage`, `/credentials/:id/edit` → `ProtectedRoute(screen="credentials.edit")` → `EditCredentialPage`, `/admin/users` → `ProtectedRoute(screen="admin.users")` → `AdminUsersPage`, `/admin/profiles` → `ProtectedRoute(screen="admin.profiles")` → `AdminProfilesPage`, `/403` → `ForbiddenPage`, `*` → redirect to `/login`
  - [x] 24.2 Create `frontend/src/pages/ForbiddenPage.tsx` with a 403 message and a link back to the user's home screen; all text via `t()`
  - Wire `RouterProvider` into `frontend/src/main.tsx` wrapping `AuthProvider`
  - _Requirements: 2.5, 3.4, 3.6, 10.1_

- [x] 25. Frontend checkpoint — ensure all frontend tests pass
  - Run `npx vitest --run` and confirm all component tests pass; fix any issues before proceeding.


- [ ] 26. Frontend component tests (Vitest + React Testing Library)
  - [ ] 26.1 Write unit tests for `PasswordInput` — Eye_Toggle toggles `type` attribute between `"password"` and `"text"`
    - _Requirements: 4.5–4.7_
  - [ ] 26.2 Write unit tests for `PasswordConfirmModal` — submit calls `onConfirm` with entered value; cancel calls `onCancel`
    - _Requirements: 4.8, 5.5, 6.5, 7.4_
  - [ ] 26.3 Write unit tests for `useVisibilityTimer` hook — after 60 s (mocked `vi.useFakeTimers`) `isVisible` becomes false; manual stop halts countdown immediately
    - _Requirements: 5.7, 5.8, 5.9_
  - [ ] 26.4 Write unit tests for `AlreadyVisibleModal` — "Continue" callback fires and "Cancel" callback fires independently
    - _Requirements: 5.10–5.12_
  - [ ] 26.5 Write unit tests for `ProtectedRoute` — non-authenticated user redirects to `/login`; User with missing screen permission redirects to `/403`; Admin always renders children
    - _Requirements: 3.4, 3.6_
  - [ ] 26.6 Write unit tests for `LanguageToggle` — clicking ES changes all `t()` output to Spanish strings; clicking EN reverts; no page reload
    - _Requirements: 10.2–10.4_
  - [ ] 26.7 Write unit tests for `ViewSearchPage` — search input with query `"git"` triggers `GET /api/credentials?q=git`; password column shows masked value by default; property test for Password_Confirmation_Prompt always shown on Eye_Toggle (Property 12, **Validates: Requirements 5.13**)
  - _Requirements: 5.1–5.14, 10.2–10.4_

- [ ] 27. Backend integration tests
  - [ ] 27.1 Write integration test `test_full_credential_lifecycle`: register → login → save credential → list → reveal → edit → delete → confirm audit_log entries for INSERT, SELECT, UPDATE, DELETE
    - _Requirements: 4.1–4.12, 5.1–5.14, 6.1–6.9, 7.1–7.7_
  - [ ] 27.2 Write integration test for admin profile assignment end-to-end: login as Admin → assign profile to User → login as User → confirm permitted and forbidden routes return expected status codes
    - _Requirements: 3.1–3.7_
  - [ ] 27.3 Write property test for concurrent operations preserve per-user isolation (Property 15)
    - **Property 15: Concurrent Operations Preserve Per-User Isolation** — simultaneous credential operations by distinct users never cross-contaminate data
    - **Validates: Requirements 8.7**
    - Uses `asyncio.gather` with in-memory SQLite via SQLAlchemy; minimum 100 iterations
  - _Requirements: 8.7_


- [ ] 28. Documentation
  - [x] 28.1 Create `README.md` in the repo root covering: project description, prerequisites (Docker, Node 18+, Python 3.11+), local setup steps, all required env variable names, `make up` / `make test-backend` / `make test-frontend` commands, and a screen-by-screen user guide (Login, Sign-Up, View/Search, Save, Edit, Delete, Admin pages, language toggle)
  - [ ] 28.2 Create `ARCHITECTURE.md` in the repo root covering: system component diagram (Mermaid), encryption lifecycle (Save → Store → Retrieve → Display), authentication and session token flow, role and profile permission model, database schema overview, Fernet key management and rotation procedure, audit log structure
  - _Requirements: 12.1–12.3_

- [ ] 29. Final checkpoint — all tests pass end-to-end
  - Run `pytest backend/` and `npx vitest --run` from the repo root; confirm zero failures across all unit, property-based, and integration tests. Ask the user if any questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints (tasks 14, 25, 29) ensure incremental validation at meaningful boundaries
- Property tests (Hypothesis) validate universal correctness guarantees; each maps 1:1 to a numbered Property in the design document
- Unit tests (pytest / Vitest + RTL) validate specific examples and edge cases
- The `app_user` DB role (task 2.2) must be configured before running the backend in any environment
- `FERNET_KEY` must be a valid 32-byte URL-safe base64 key; generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- JWT tokens are stored in React memory only (AuthContext) — never in `localStorage` or cookies

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1"] },
    { "id": 1, "tasks": ["2.2", "3.1"] },
    { "id": 2, "tasks": ["3.2"] },
    { "id": 3, "tasks": ["5.1", "6.1", "7.1", "7.2", "8.1", "11.1"] },
    { "id": 4, "tasks": ["5.2", "6.2", "6.3", "6.4", "6.5", "6.6", "7.3", "7.4", "8.2", "8.3", "11.2", "13.1"] },
    { "id": 5, "tasks": ["11.3", "11.4", "11.5", "15.1", "17.1", "17.2"] },
    { "id": 6, "tasks": ["15.2", "15.3", "16.1", "16.2", "16.3", "16.4", "16.5", "16.6", "16.7"] },
    { "id": 7, "tasks": ["21.1", "21.2", "21.3", "21.4", "23.1", "23.2", "24.1"] },
    { "id": 8, "tasks": ["24.2", "26.1", "26.2", "26.3", "26.4", "26.5", "26.6"] },
    { "id": 9, "tasks": ["26.7", "27.1", "27.2", "27.3", "28.1", "28.2"] }
  ]
}
```
