# Implementation Plan: Password Manager Website

## Overview

Full-stack implementation of a secure password manager using FastAPI (Python) on the backend and React + TypeScript (Vite) on the frontend. Tasks are organized incrementally — infrastructure and data layer first, then backend services, then API routers, then frontend pages, then tests. Every task builds on the previous ones and all code is wired together by the final integration step.

## Tasks

- [x] 1. Project scaffolding and monorepo structure
  - Create root-level `docker-compose.yml` with services: `db` (postgres:15), `backend` (FastAPI), `frontend` (Vite dev server)
  - Create `.env.example` with all required env vars: `DATABASE_URL`, `FERNET_KEY`, `JWT_SECRET`, `JWT_ALGORITHM=HS256`, `JWT_EXPIRE_MINUTES=15`, `CORS_ORIGINS`
  - Create `backend/` directory with `requirements.txt` pinning: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg2-binary`, `cryptography`, `passlib[bcrypt]`, `python-jose[cryptography]`, `python-dotenv`, `hypothesis`, `pytest`, `pytest-asyncio`, `httpx`
  - Create `frontend/` directory bootstrapped with `npm create vite@latest` using the `react-ts` template; install `react-router-dom`, `react-i18next`, `i18next`, `axios`, `tailwindcss`, `postcss`, `autoprefixer`; initialize Tailwind config
  - Create root-level `Makefile` with targets: `up`, `down`, `test-backend`, `test-frontend`
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
  - [x]* 5.2 Write property test for credential encryption invariant (Property 9)
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
  - [x]* 6.2 Write property test for password confirmation match (Property 1)
    - **Property 1: Password Confirmation Match** — register accepts iff `password == password_confirmation`
    - **Validates: Requirements 1.3, 1.4**
    - Minimum 100 Hypothesis iterations
  - [x]* 6.3 Write property test for password strength validation (Property 2)
    - **Property 2: Password Strength Validation** — validator rejects iff at least one rule (length, uppercase, lowercase, digit, symbol) is unmet
    - **Validates: Requirements 1.5, 1.6**
    - Minimum 200 Hypothesis iterations; generate strings with `st.text()`
  - [x]* 6.4 Write property test for account password hashing (Property 3)
    - **Property 3: Account Password Hashing** — stored `password_hash` is a valid bcrypt hash and differs from plaintext
    - **Validates: Requirements 1.7, 8.5**
    - Minimum 100 Hypothesis iterations
  - [x]* 6.5 Write property test for JWT issued on successful login (Property 6)
    - **Property 6: JWT Issued on Successful Login** — response contains `access_token` with `user_id`, `role`, and `exp` within 15 min
    - **Validates: Requirements 2.4**
    - Minimum 100 Hypothesis iterations
  - [x]* 6.6 Write property test for generic error on invalid login (Property 5)
    - **Property 5: Generic Error on Invalid Login** — all failed login attempts return the same generic response body
    - **Validates: Requirements 2.3**
    - Minimum 100 Hypothesis iterations
  - _Requirements: 1.3–1.7, 2.2–2.4, 8.5_

- [x] 7. AuditService and audit column helpers
  - [x] 7.1 Create `backend/app/services/audit_service.py` implementing `AuditService.log(user_id, operation, affected_record_id)` that writes a row to `audit_log` and commits synchronously; `operation` must be one of `SELECT|INSERT|UPDATE|DELETE`
  - [x] 7.2 Create `backend/app/utils/audit_columns.py` with `set_creation_audit(record, user_id)` and `set_modification_audit(record, user_id)` helper functions that populate the six audit column fields with `date.today()` and `datetime.utcnow().time()`
  - [x]* 7.3 Write property test for audit columns on creation (Property 4)
    - **Property 4: Audit Columns on Creation** — `creation_date`, `creation_time`, `creation_user_id` are all non-null after any record creation
    - **Validates: Requirements 1.8, 4.11, 9.8**
    - Minimum 100 Hypothesis iterations using mocked DB session
  - [x]* 7.4 Write property test for audit log entry on every mutation and reveal (Property 13)
    - **Property 13: Audit Log Entry on Every Mutation and Reveal** — after each INSERT/SELECT/UPDATE/DELETE operation an `audit_log` row exists with correct `operation`, `user_id`, and `affected_record_id`
    - **Validates: Requirements 4.12, 5.14, 6.9, 7.7**
    - Minimum 100 Hypothesis iterations
  - _Requirements: 1.8, 4.11, 4.12, 5.14, 6.8, 6.9, 7.7, 9.5, 9.8_

- [x] 8. ProfileService
  - [x] 8.1 Create `backend/app/services/profile_service.py` implementing:
    - `get_user_permissions(user_id: int) -> list[str]`: queries `user_profiles` → `profiles.permitted_screens`; returns `["*"]` for Admin role
    - `assign_profile(admin_id: int, user_id: int, profile_id: int)`: updates or inserts `user_profiles` row, calls `set_modification_audit`, commits
  - [x]* 8.2 Write property test for non-admin denied access to admin endpoints (Property 7)
    - **Property 7: Non-Admin Denied Access to Admin Screens** — any JWT with `role="User"` receives HTTP 403 on all `/api/admin/*` endpoints
    - **Validates: Requirements 3.2, 3.4, 3.6**
    - Minimum 100 Hypothesis iterations using `httpx` TestClient
  - [x]* 8.3 Write property test for profile assignment updates audit columns (Property 8)
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
  - [x]* 11.3 Write property test for credential ownership isolation (Property 10)
    - **Property 10: Credential Ownership Isolation** — user U cannot list, reveal, edit, or delete any credential owned by user V
    - **Validates: Requirements 5.3, 8.2**
    - Minimum 100 Hypothesis iterations
  - [x]* 11.4 Write property test for search filter correctness (Property 11)
    - **Property 11: Search Filter Correctness** — every returned credential contains query Q as case-insensitive substring in `website_name` or `email_or_username`
    - **Validates: Requirements 5.2**
    - Minimum 200 Hypothesis iterations
  - [x]* 11.5 Write property test for wrong account password rejects sensitive operations (Property 14)
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
  - [x]* 13.1 Write property test for email validation (Property 16)
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

- [x] 26. Frontend component tests (Vitest + React Testing Library)
  - [x] 26.1 Write unit tests for `PasswordInput` — Eye_Toggle toggles `type` attribute between `"password"` and `"text"`
    - File: `frontend/src/components/__tests__/PasswordInput.test.tsx`
    - _Requirements: 4.5–4.7_
  - [x] 26.2 Write unit tests for `PasswordConfirmModal` — submit calls `onConfirm` with entered value; cancel calls `onCancel`; password field uses `PasswordInput` with working Eye_Toggle
    - Create `frontend/src/components/__tests__/PasswordConfirmModal.test.tsx`
    - Render `<PasswordConfirmModal onConfirm={...} onCancel={...} />`, type a password, click confirm — assert `onConfirm` called with the typed value
    - Assert clicking cancel calls `onCancel` and not `onConfirm`
    - _Requirements: 4.8, 5.5, 6.5, 7.4_
  - [x] 26.3 Write unit tests for `useVisibilityTimer` hook — after 60 s (mocked `vi.useFakeTimers`) `isVisible` becomes false; manual stop halts countdown immediately
    - File: `frontend/src/hooks/__tests__/useVisibilityTimer.test.ts`
    - _Requirements: 5.7, 5.8, 5.9_
  - [x] 26.4 Write unit tests for `AlreadyVisibleModal` — "Continue" callback fires and "Cancel" callback fires independently
    - File: `frontend/src/components/__tests__/AlreadyVisibleModal.test.tsx`
    - _Requirements: 5.10–5.12_
  - [x] 26.5 Write unit tests for `ProtectedRoute` — non-authenticated user redirects to `/login`; User with missing screen permission redirects to `/403`; Admin always renders children
    - Create `frontend/src/components/__tests__/ProtectedRoute.test.tsx`
    - Mock `useAuth()` to return null token → assert `<Navigate to="/login" />` is rendered
    - Mock `useAuth()` to return a User JWT and mock `GET /api/profile/permissions` to return a list that excludes the requested screen → assert `<Navigate to="/403" />` is rendered
    - Mock `useAuth()` to return an Admin JWT → assert children are rendered without any redirect
    - _Requirements: 3.4, 3.6_
  - [x] 26.6 Write unit tests for `LanguageToggle` — clicking ES changes all `t()` output to Spanish strings; clicking EN reverts; no page reload
    - Create `frontend/src/components/__tests__/LanguageToggle.test.tsx`
    - Wrap component in `I18nextProvider`; click the ES button; query a translated text node and assert it matches the Spanish value from `es.json`; click EN and assert it reverts to the English value
    - Assert `window.location.reload` is never called during language change
    - _Requirements: 10.2–10.4_
  - [x] 26.7 Write unit tests for `ViewSearchPage` — search input with query `"git"` triggers `GET /api/credentials?q=git`; password column shows masked value by default
    - Create `frontend/src/pages/__tests__/ViewSearchPage.test.tsx`
    - Mock `apiClient` to return a fixture credential list; render `<ViewSearchPage />`; type `"git"` in the search box; assert `GET /api/credentials?q=git` was called
    - Assert the password cell value is `"••••••••"` (or hidden `<input type="password">`) before any Eye_Toggle is clicked
    - **Property 12: Password Confirmation Always Required for Reveal** — click Eye_Toggle twice on the same row (after masking); assert `PasswordConfirmModal` appears both times
    - **Validates: Requirements 5.13**
    - _Requirements: 5.1–5.14_
  - _Requirements: 5.1–5.14, 10.2–10.4_

- [x] 27. Backend integration tests
  - [x] 27.1 Write integration test `test_full_credential_lifecycle` in `backend/tests/test_integration.py`
    - Use `httpx.AsyncClient` with `TestClient` against an in-memory SQLite DB (override `get_db` dependency)
    - Steps: `POST /api/auth/register` → `POST /api/auth/login` → `POST /api/credentials` → `GET /api/credentials` → `POST /api/credentials/{id}/reveal` → `PUT /api/credentials/{id}` → `DELETE /api/credentials/{id}`
    - After each mutating step, query `audit_log` and assert a row exists with correct `operation`, `user_id`, and `affected_record_id`
    - _Requirements: 4.1–4.12, 5.1–5.14, 6.1–6.9, 7.1–7.7_
  - [x] 27.2 Write integration test for admin profile assignment end-to-end in `backend/tests/test_integration.py`
    - Register an Admin user and a regular User; Admin logs in and calls `PUT /api/admin/users/{user_id}/profile`
    - Log in as the User and assert that only the permitted routes return 200; assert that routes outside the assigned profile return 403
    - _Requirements: 3.1–3.7_
  - [x] 27.3 Write property test for concurrent operations preserving per-user isolation (Property 15) in `backend/tests/test_property_15_concurrency.py`
    - **Property 15: Concurrent Operations Preserve Per-User Isolation** — simultaneous credential operations by distinct users never cross-contaminate data
    - **Validates: Requirements 8.7**
    - Use `asyncio.gather` with SQLAlchemy in-memory SQLite; create two users, run concurrent save/list/reveal operations; assert each user's response list contains only their own credentials
    - Minimum 100 Hypothesis iterations
  - _Requirements: 8.7_

- [x] 28. Documentation
  - [x] 28.1 Create `README.md` in the repo root covering: project description, prerequisites (Docker, Node 18+, Python 3.11+), local setup steps, all required env variable names, `make up` / `make test-backend` / `make test-frontend` commands, and a screen-by-screen user guide (Login, Sign-Up, View/Search, Save, Edit, Delete, Admin pages, language toggle)
  - [x] 28.2 Create `ARCHITECTURE.md` in the repo root with the following sections:
    - **System Component Diagram**: reproduce the Mermaid `graph TD` from the design showing Browser → Backend routers → Services → PostgreSQL
    - **Encryption Lifecycle**: describe the Save → Store → Retrieve → Display flow with the Fernet key source and the guarantee that plaintext never touches the DB
    - **Authentication and Session Token Flow**: reproduce the Mermaid `sequenceDiagram` for login; explain JWT claims (`user_id`, `role`, `exp`), 15-minute expiry, in-memory storage in React, and the redirect-on-401 behavior
    - **Role and Profile Permission Model**: explain the two roles, the `profiles.permitted_screens` JSONB field, the backend `require_permission` dependency, and the frontend `ProtectedRoute` HOC
    - **Database Schema Overview**: describe all five tables and the six audit columns; include the ERD Mermaid diagram from the design
    - **Fernet Key Management and Rotation**: document how to generate a key with `Fernet.generate_key()`, how to store it in `FERNET_KEY` env var, and the rotation procedure (re-encrypt all `credentials.encrypted_password` rows with the new key before swapping the env var)
    - **Audit Log Structure**: describe the `audit_log` table columns and the four logged events (INSERT/SELECT/UPDATE/DELETE) with their triggers
    - _Requirements: 12.3_
  - _Requirements: 12.1–12.3_

- [x] 29. Final checkpoint — all tests pass end-to-end
  - Run `pytest backend/` and `npx vitest --run` from the repo root; confirm zero failures across all unit, property-based, and integration tests. Ask the user if any questions arise.
  - Closed 2026-11-13 after tasks 30–31: backend 166/166, frontend 86/86, Playwright E2E 2/2 (`npx playwright test`). Not yet run against PostgreSQL/Docker.

- [x] 30. Phase 1 — MVP unblock (Claude Code handover audit, 2026-11-12)
  - Audit found the app unusable end-to-end although tasks 1–27 were checked: unit/integration tests mocked every frontend↔backend boundary and promoted test users to Admin, hiding missing endpoints and seed data.
  - [x] 30.0 Fix backend test isolation: per-module `get_db` overrides collided at collection time (7 failures in the full suite); add `tests/conftest.py`; make `profiles.permitted_screens` JSON-portable so SQLite tests can create every table
  - [x] 30.1 B1 — add `username` claim to the JWT (frontend `AuthContext` discarded tokens without it, so login always bounced back to `/login`)
    - _Requirements: 2.2, 2.4_
  - [x] 30.2 B2 — `GET /api/profile/permissions` (called by `ProtectedRoute`; missing → every User-role page redirected to `/403`)
    - _Requirements: 3.4, 3.6_
  - [x] 30.3 B3 — `GET /api/credentials/{id}` with ownership check and `password: null` (Edit page could not load)
    - _Requirements: 6.2_
  - [x] 30.4 B4 — `GET /api/admin/profiles`; Admin pages load real profiles instead of hard-coded ids; `/api/admin/*` restricted to Admin role via `require_admin`
    - _Requirements: 3.2, 3.5, 3.7; Property 7_
  - [x] 30.5 B5 — idempotent seed of profiles Basic/Full on startup, `DEFAULT_PROFILE` for new sign-ups, `python -m app.cli create-admin|promote|seed`
    - _Requirements: 3.1–3.4_
  - [x] 30.6 B6 — wrong account password in the confirmation modal no longer logs the user out (interceptor skips the documented 401 detail)
    - _Requirements: 4.9, 5.5, 6.6, 7.5_
  - [x] 30.7 B7 — `AppLayout` header: language toggle on every page, permission-filtered navigation, current user, logout
    - _Requirements: 3.4, 10.2_
  - [x] 30.8 Frontend build hygiene: 33 TypeScript errors in tests and the failing `PasswordInput` test fixed (`npm run build` runs `tsc`)
  - [x] 30.9 Contract tests `backend/tests/test_mvp_contract.py`; frontend tests for `AppLayout` and `apiClient`
  - [x] 30.10 Playwright E2E (`frontend/e2e/mvp.e2e.ts`, `make test-e2e`) against real uvicorn + Vite: user lifecycle and admin profile reassignment

- [x] 31. Phase 2 — Security hardening
  - [x] 31.1 Fail fast on missing/weak `JWT_SECRET` (< 32 chars or known weak value) and invalid `FERNET_KEY` (`app/security.py › validate_settings`, run in the app lifespan); no more `"changeme"` fallback
    - _Requirements: 8.1, 8.3_
  - [x] 31.2 Replace unmaintained `python-jose` + `passlib` with PyJWT + `bcrypt`; existing `$2b$` hashes keep verifying; unknown usernames still run bcrypt (no timing enumeration); access tokens require `exp` and `type="access"`
    - _Requirements: 1.7, 2.3, 2.4, 8.5_
  - [x] 31.3 Rate limiting with slowapi: login 10/min, register 5/min, refresh 30/min per IP; save/reveal/edit/delete 10/min per user (account-password brute force); 429 `"Too many attempts…"`
    - _Requirements: 2.3, 4.9, 5.5, 6.6, 7.5_
  - [x] 31.4 Credential mutation and its `audit_log` row committed in one transaction (`AuditService.log(commit=False)`)
    - _Requirements: 4.12, 6.9, 7.7, 8.7_
  - [x] 31.5 Refresh token in an httpOnly, Secure, SameSite=Strict cookie scoped to `/api/auth`: `POST /api/auth/refresh` (rotation + reuse detection), `POST /api/auth/logout` (revocation); new `refresh_tokens` table (SHA-256 only); frontend silent refresh + retry and session restore after reload. Access token still lives only in memory
    - _Requirements: 2.4, 2.5, 8.3_
  - [x] 31.6 Alembic migrations (`backend/migrations`) are the schema source of truth; app no longer calls `create_all`; Docker/E2E run `alembic upgrade head`; `db/schema.sql` regenerated from migrations; `tests/test_migrations.py` fails on model/migration drift
    - _Requirements: 9.1–9.9_
  - [x] 31.7 npm dependencies updated (axios 1.21.0, vite 6.4.5, vitest 4.1.12, react-router-dom 6.30.6, @playwright/test 1.59.1): 0 high vulnerabilities
  - [x] 31.8 Upgrade react-router to v7 to clear the remaining moderate advisory (open redirect via backslash in `<Link>`/`useNavigate`; was not reachable — the app only navigates to static paths). Done in 34.1

- [x] 32. Phase 4 — Deployment and continuous quality
  - [x] 32.1 Linters: ruff (backend, `ruff.toml`) and ESLint 9 flat config with react-hooks rules (frontend); both clean
  - [x] 32.2 GitHub Actions CI (`.github/workflows/ci.yml`): lint, pip-audit, npm audit, pytest (SQLite), migrations + API tests on PostgreSQL 15, Vitest, build, Playwright on PostgreSQL, production smoke test
  - [x] 32.3 Deprecated APIs and timestamp consistency: Pydantic `ConfigDict`; audit dates and times both taken from one UTC instant (`utc_date_time`), previously local date + UTC time
    - _Requirements: 9.8_
  - [x] 32.4 Search: `pg_trgm` GIN indexes (migration 0003) serve `ILIKE '%q%'`; LIKE wildcards in the query are escaped
    - _Requirements: 5.2, 9.7_
  - [x] 32.5 Fernet key rotation without downtime: multi-key `FERNET_KEY` and `python -m app.cli rotate-fernet-key [--dry-run]` (all rows or none)
    - _Requirements: 8.1_
  - [x] 32.6 Production stack `docker-compose.prod.yml`: Caddy (TLS, HSTS, CSP), one-shot `migrate`, backend non-root as `app_user` (DML only), `/api/health`
    - _Requirements: 8.4, 9.9_
  - [x] 32.7 Verified against PostgreSQL (local 18 and CI 15): migrations, API/security/rotation tests, Playwright E2E, app_user privileges; `scripts/smoke-prod.sh` checks the Docker stack in CI
  - [x] 32.8 Python dependencies with known vulnerabilities upgraded (fastapi 0.162 / starlette 1.10, cryptography 50, PyJWT 2.15, python-multipart 0.0.32, python-dotenv 1.2.4, pytest 9.2, SQLAlchemy 2.0.55, psycopg2-binary 2.9.10): pip-audit clean
  - [x] 32.9 Fixed an intermittent failure in the Property 10 tests (stale objects in a long-lived test session)

- [x] 33. Phase 5 — Spec Phase 2: email verification, deactivation and CAPTCHA
  - [x] 33.1 Settings (`app/phase2.py`): `EMAIL_VERIFICATION_ENABLED`, `APP_BASE_URL`, `VERIFICATION_TOKEN_HOURS`, `EMAIL_BACKEND`, `SMTP_*`, `HCAPTCHA_SITE_KEY`/`HCAPTCHA_SECRET`; off by default, half-configured settings stop startup; `GET /api/auth/config`
  - [x] 33.2 `email_verification_tokens` (migration 0004) and `EmailVerificationService`: one-time hashed links, 48 h; sign-up sets `deactivation_deadline` = creation + 30 days and sends the email; `POST /api/auth/verify-email`
    - _Requirements: 1.9, 1.10_
  - [x] 33.3 Email delivery (`email_sender.py`): console / SMTP (STARTTLS, SSL) / file backends, sent after the response, failures logged; English and Spanish texts
    - _Requirements: 1.10_
  - [x] 33.4 hCaptcha on login: widget loaded only when configured, `captcha_token` verified server-side before the password, fails closed; CSP allows hcaptcha.com
    - _Requirements: 2.6_
  - [x] 33.5 Frontend: verification modal after login with resend (`POST /api/profile/verification-email`, 3/hour), `/verify-email` page, deactivated-account and CAPTCHA messages, sign-up confirmation; EN/ES
    - _Requirements: 2.7, 2.8_
  - [x] 33.6 Deactivation: unverified past the deadline → login 403, refresh 401, link 403; resend never moves the deadline; `python -m app.cli verify-email` reactivates
    - _Requirements: 2.8, 2.9_
  - [x] 33.7 Tests: `test_phase2_verification.py` (43, also on PostgreSQL in CI), Vitest for login/modal/page, Playwright flow with verification on (email, resend, deactivation, CLI reactivation, one-time link)

- [x] 34. Phase 6 — Operations: dependencies, shared rate limits, backups, reminders
  - [x] 34.1 react-router 7.18.5 (package `react-router`, `RouterProvider` from `react-router/dom`) replaces react-router-dom 6 and clears its advisory (closes 31.8); ESLint 9.39 / typescript-eslint 8.72
  - [x] 34.2 Redis for rate-limit counters in production (`redis` service, 2 uvicorn workers); in-memory per-IP fallback (`RATE_LIMIT_FALLBACK`) while Redis is unreachable; tests on Redis in CI
    - _Requirements: 2.3, 8.1_
  - [x] 34.3 Automated PostgreSQL backups (`backup` service: daily `pg_dump`, verified, 14-day retention) and `scripts/restore-backup.sh` (one transaction, keeps `app_user` grants); verified on PostgreSQL and in the production smoke test
    - _Requirements: 9.9_
  - [x] 34.4 Verification deadline reminders: `send-verification-reminders` CLI run hourly by the `scheduler` service, 7 and 1 days before (`VERIFICATION_REMINDER_DAYS`), once each, in the user's language (migration 0005: `preferred_language`, `last_verification_reminder_days`)
    - _Requirements: 1.9, 1.10, 2.8_
  - [x] 34.5 Production smoke test extended: shared login limit through Redis, backup → data loss → restore → reveal, reminder sent by the scheduler as `app_user`
  - [x] 34.6 Fix: the Redis rate-limit test and the smoke test looked for keys `LIMITER*`, but `limits` stores them as `LIMITS:LIMITER/…` (first CI run of 34 failed on that assertion; the limiter itself was correct)

- [ ] 35. Backlog — pending after the 2026-11-14 review (not started)
  - New features (35.5–35.8) are outside the Kiro requirements: add them to `requirements.md` / `design.md` before implementing.
  - [ ] 35.1 ~~First deployment on a real server~~ — omitted by the owner (2026-11-14); replaced by the local installation, task 36
  - [ ] 35.2 ~~Off-site (cloud) backup copies~~ — omitted by the owner (2026-11-14); the local installation keeps encrypted backups in `Backup\db` (task 36.4)
    - _Requirements: 9.9_
  - [ ] 35.3 Monitoring and alerts: external check of `/api/health`, alert when a backup or reminder run fails, log retention
  - [ ] 35.4 GitHub Actions: move `actions/checkout`, `setup-python`, `setup-node`, `upload-artifact` to releases that run on Node 24 (Node 20 is deprecated on the runners)
  - [ ] 35.5 → moved to 37.5. "Forgot password": email reset link (one-time, short-lived), revokes refresh tokens; works because credentials are encrypted with the server key, not with the account password
  - [ ] 35.6 → moved to 37.5. Two-factor authentication (TOTP) at login, with recovery codes
  - [x] 35.7 Password generator on the Save / Edit credential pages (Requirement 18)
  - [ ] 35.8 Self-service: export my credentials (re-entering the account password, audited) and delete my account
  - [ ] 35.9 Decide the encryption model: today the server decrypts with `FERNET_KEY` (database + key leak exposes every password). Client-side encryption with a key derived from the account password (zero-knowledge) would remove that risk but rules out 35.5 and needs a redesign — decide before real users
  - [ ] 35.10 Lint tooling advisory: drop when `typescript-eslint` moves to `minimatch` 11 (moderate ReDoS, dev-only)

- [ ] 36. Local installation on Windows — same model as Savings Tool phase 8 (`docs/local-install.md`)
  - [x] 36.1 `scripts/release.py --to Y:\Apps\Save-Pass`: settings template with fresh secrets, private Python runtime (Network Service cannot use a per-user Python), same-origin frontend build, settings check, migrations as the migrator role, swap with `app.old`, web folder sync, jobs copied
  - [x] 36.2 Own PostgreSQL 18 cluster `savepass-postgres` on 127.0.0.1:5435 with `savepass_migrator` / `savepass_app` (DML only) / `savepass_backup` roles (`ops/windows/01-postgres.ps1`)
    - _Requirements: 9.9_
  - [x] 36.3 IIS site on HTTPS 8443 (443 is Savings Tool) with URL Rewrite + ARR: `/api` proxy, SPA fallback, Caddy-equivalent security headers (`deploy/iis/web.config.template`); mkcert certificate from Savings Tool's authority; firewall Private only; power settings (`02`–`04`)
    - _Requirements: 8.4_
  - [x] 36.4 Scheduled tasks as Network Service (`05-tasks.ps1`): API at startup, encrypted daily backup (AES-256-GCM, 14 daily + 12 monthly), weekly restore test, verification reminders
  - [x] 36.5 Per-device rate limits behind IIS: `CLIENT_IP_HEADER=X-Client-IP`, trusted only from 127.0.0.1
    - _Requirements: 2.3_
  - [x] 36.6 Tools: `update-ip.cmd`, `reset-postgres-password.cmd`, `with-production.ps1`, `00-check.ps1`; development start/stop with one double click (`ops/local`, auto-stop after 30 min); dev ports only on 127.0.0.1, database on 5436 (5432 is a native service)
  - [x] 36.7 Rehearsed without administrator rights (two releases, API from the installed folder, privileges, backup + restore test, CLI); `tests/test_local_install.py`, client-IP tests
  - [ ] 36.8 Owner runs the administrator steps on the laptop (01, 02–05) and tests on the laptop and the phone

- [x] 37. Bring Savings Tool's administration, screens and personal settings to Save-Pass (owner's decisions of 2026-11-15: open sign-up, mandatory 2FA, password still asked on every credential reveal/edit/delete with idle and maximum session limits, one role per account, order 37.1 → 37.6)
  - [x] 37.1 Per-action permissions with two fixed roles: `app/permissions.py`, every endpoint asks for one (no Admin bypass, role read from the database), profiles retired (migration 0006), Admin page changes roles (not their own), menu and routes by permission
    - _Requirements: 3.1–3.7_
  - [x] 37.2 Application shell and interface patterns: grouped side menu (collapsible, drawer on the phone), account menu, Home, lists with search / filters / pagination / list-grid, form patterns
    - _Requirements: 13.1–13.5_
  - [x] 37.3 Appearance and personal settings: Settings screen (profile, preferences, password, active sessions), light/dark/system theme, accent colors, avatar, private mode, user ID `SP-XXXXXX`
    - _Requirements: 14.1–14.5_
  - [x] 37.4 User administration and audit view: search and filters, deactivate with reason, reactivate, audit view (unlock and reset 2FA moved to 37.5, which brings lockout and TOTP)
    - _Requirements: 15.1–15.4_
  - [x] 37.5 Account security and system parameters: mandatory TOTP with recovery codes, lockout and unlock (with the Admin's unlock and 2FA reset and the "locked" status filter from 15.1–15.2), forgot password, idle and maximum session limits with warning and extend, re-authentication window for administration, clipboard clearing, security emails, System parameters screen (absorbs 35.5 and 35.6)
    - _Requirements: 16.1–16.8_
  - [x] 37.6 In-app help: user guide with search, technical guide for the Admin
    - _Requirements: 17.1–17.2_

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
    { "id": 8, "tasks": ["24.2", "26.1", "26.3", "26.4"] },
    { "id": 9, "tasks": ["26.2", "26.5", "26.6", "27.3"] },
    { "id": 10, "tasks": ["26.7", "27.1", "27.2", "28.2"] }
  ]
}
```
