# Save-Pass — guía para Claude Code

Gestor de contraseñas full-stack. Proyecto iniciado con Kiro (spec-driven) y continuado con Claude Code.

## Fuente de verdad (specs)

- `.kiro/specs/password-manager-website/requirements.md` — requisitos (EARS, numerados 1.x–12.x)
- `.kiro/specs/password-manager-website/design.md` — arquitectura, DDL, contratos de API, 16 "Properties" de corrección
- `.kiro/specs/password-manager-website/tasks.md` — plan de tareas con checkboxes `[x]` / `[ ]`

Reglas:
- Al completar una tarea, marca su checkbox en `tasks.md` (mismo commit que el código).
- Tareas nuevas que no estaban en Kiro van como secciones nuevas al final de `tasks.md` (numeración 30+), referenciando requisitos.
- Si un cambio contradice `design.md`, actualiza `design.md` en el mismo commit y explica por qué en el mensaje.
- `tasks.meta.json` y `.config.kiro` son metadatos de Kiro: no editarlos a mano.
- Estado (2026-11-16): tareas 1–34 hechas; la 35 es el backlog (35.1 y 35.2 omitidas; 35.5 y 35.6 pasaron a 37.5); la 36 es la instalación local en Windows (instalada; falta la prueba en el celular); la 37 trae lo de Savings Tool en el orden 37.1 → 37.6 (37.1 roles y permisos, 37.2 menú y patrones de pantalla, 37.3 configuración, tema y sesiones: hechas). Decisiones del dueño: registro abierto, 2FA obligatorio para todos, la contraseña se pide en cada revelar/editar/borrar, un solo rol por persona (User o Admin). Las funciones nuevas de 35.5–35.8 necesitan requisitos en `requirements.md` y diseño en `design.md` antes de implementarse.

## Stack

- Backend: Python 3.11+ · FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · `cryptography` (Fernet) · bcrypt · PyJWT (HS256) · slowapi
- Frontend: React 18 · TypeScript · Vite · Tailwind 3 · react-i18next (EN/ES) · axios · react-router v7 (paquete `react-router`)
- DB: PostgreSQL 15 (tests usan SQLite en memoria)
- Docker Compose dev: `db`, `backend` (:8000), `frontend` (:5173). Prod: `docker-compose.prod.yml` (Caddy HTTPS, `migrate`, backend como `app_user` con 2 workers, Redis para rate limit, db, `backup` diario, `scheduler` de recordatorios)
- CI: `.github/workflows/ci.yml`

## Comandos

```bash
# backend (desde backend/)
python -m pytest tests/ -q            # incluye Hypothesis; tarda varios minutos
python -m pytest tests/test_integration.py -q

# frontend (desde frontend/)
npx vitest --run
npx tsc --noEmit                      # debe quedar en 0 errores: `npm run build` ejecuta tsc
npm run build
npx playwright test                   # E2E: levanta uvicorn :8001 (SQLite) + Vite :5174 solo

# migraciones (desde backend/) — única fuente del esquema
alembic upgrade head
alembic revision --autogenerate -m "..."   # tras cambiar app/models.py
python db/generate_schema_sql.py          # regenera db/schema.sql

# admin (desde backend/)
python -m app.cli create-admin --username admin --email admin@example.com
python -m app.cli promote --username alice
python -m app.cli verify-email --username alice   # marca el email verificado / reactiva

# lint
cd backend && ruff check .            # 0 errores
cd frontend && npm run lint           # 0 avisos

# PostgreSQL (tests de API contra una BD desechable: se borra)
TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_mvp_contract.py tests/test_security_hardening.py tests/test_key_rotation.py tests/test_phase2_verification.py -q
E2E_POSTGRES_URL=postgresql://... npx playwright test

# producción
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
./scripts/smoke-prod.sh               # requiere Docker; CI lo ejecuta en cada push
python -m app.cli rotate-fernet-key   # con FERNET_KEY="<nueva>,<vieja>"
make backup                          # backup ahora; ./scripts/restore-backup.sh <dump> restaura

# instalación local en Windows (tarea 36, docs/local-install.md)
python scripts/release.py --to Y:\Apps\Save-Pass   # instala o actualiza (terminal de administrador al actualizar)
powershell -ExecutionPolicy Bypass -File ops\windows\00-check.ps1   # revisa sin cambiar nada; 01-05 como administrador
ops\local\start-local.cmd / stop-local.cmd      # desarrollo con Docker, se apaga solo a los 30 min
python -m app.cli send-verification-reminders [--dry-run]   # el servicio scheduler lo corre cada hora

# todo
make up / make down / make test-backend / make test-frontend / make lint
```

## Convenciones

- Commits: Conventional Commits (`feat(frontend): …`, `fix(backend): …`, `test: …`, `docs(tasks): …`).
- Toda operación sensible (save/reveal/edit/delete) re-verifica la contraseña de cuenta y escribe en `audit_log`.
- Permisos: cada endpoint pide un permiso de `app/permissions.py` con `require_permission(...)`; nada de excepciones por rol. Un permiso nuevo se agrega ahí, al rol que corresponde y a `tests/test_permissions.py`. Ningún rol ve las credenciales de otra persona.
- Pantallas: cada entrada del menú se declara en `frontend/src/config/navigation.tsx` con su grupo y permiso; las listas usan `SearchBox`/`FilterSelect`/`ViewToggle`/`Pagination` + `usePaged` + `useListView` (búsqueda sin acentos con `lib/text.ts`); los formularios usan `HelpTip`, `aria-invalid` y `useFocusFirstError`.
- Tema: los colores `gray/red/green/amber/yellow/indigo/white` salen de variables CSS (`src/theme.css`, generado con `node scripts/generate-theme.mjs`); el modo oscuro invierte las paletas, así que no hace falta `dark:` en las páginas; `indigo` es el color de acento.
- Sesiones: el access token lleva `sid` (familia de refresh tokens); al terminar la sesión deja de valer de inmediato.
- El JWT vive solo en memoria (nunca localStorage/cookies legibles por JS).
- Todo texto de UI va por `t()`; cualquier clave nueva se añade a `en.json` y `es.json`.
- Contratos de API: si el frontend llama a un endpoint, el backend debe tenerlo registrado y con test de integración.
- Esquema: nunca `create_all` en la app; todo cambio de modelo va con su migración Alembic (`tests/test_migrations.py` lo exige).
- Secretos: la app no arranca sin `JWT_SECRET` (≥ 32) y `FERNET_KEY` válidos; los tests desactivan el rate limit en `conftest.py`.
- Dependencias: versiones exactas y publicadas hace ≥ 2 semanas; CI falla con vulnerabilidades (pip-audit, npm audit high).
- Fechas y horas de auditoría en UTC desde un mismo instante (`utc_date_time()` en `app/utils/audit_columns.py`).
- Fase 2 del spec (verificación de email, CAPTCHA) apagada por defecto: `EMAIL_VERIFICATION_ENABLED`, `HCAPTCHA_SITE_KEY`/`HCAPTCHA_SECRET`; la E2E la ejecuta encendida (emails en `backend/e2e-outbox/`).
- Instalación local: mismo modelo que Savings-Tool (fase 8). Puertos: 8443 (IIS), 8010 (API), 5435 (BD instalada), 5436 (BD de desarrollo); 443/3000/5433/5434 son de Savings-Tool. Nada en `C:` (datos en `Y:\Apps\Save-Pass` y `Backup\`).
- No commitear `.env`, `.hypothesis/`, `.pytest_cache/`, `node_modules/`.
