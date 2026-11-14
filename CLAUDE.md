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

## Stack

- Backend: Python 3.11+ · FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · `cryptography` (Fernet) · bcrypt · PyJWT (HS256) · slowapi
- Frontend: React 18 · TypeScript · Vite · Tailwind 3 · react-i18next (EN/ES) · axios · react-router v6
- DB: PostgreSQL 15 (tests usan SQLite en memoria)
- Docker Compose dev: `db`, `backend` (:8000), `frontend` (:5173). Prod: `docker-compose.prod.yml` (Caddy HTTPS, `migrate`, backend como `app_user`, db)
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

# lint
cd backend && ruff check .            # 0 errores
cd frontend && npm run lint           # 0 avisos

# PostgreSQL (tests de API contra una BD desechable: se borra)
TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_mvp_contract.py tests/test_security_hardening.py tests/test_key_rotation.py -q
E2E_POSTGRES_URL=postgresql://... npx playwright test

# producción
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
./scripts/smoke-prod.sh               # requiere Docker; CI lo ejecuta en cada push
python -m app.cli rotate-fernet-key   # con FERNET_KEY="<nueva>,<vieja>"

# todo
make up / make down / make test-backend / make test-frontend / make lint
```

## Convenciones

- Commits: Conventional Commits (`feat(frontend): …`, `fix(backend): …`, `test: …`, `docs(tasks): …`).
- Toda operación sensible (save/reveal/edit/delete) re-verifica la contraseña de cuenta y escribe en `audit_log`.
- El JWT vive solo en memoria (nunca localStorage/cookies legibles por JS).
- Todo texto de UI va por `t()`; cualquier clave nueva se añade a `en.json` y `es.json`.
- Contratos de API: si el frontend llama a un endpoint, el backend debe tenerlo registrado y con test de integración.
- Esquema: nunca `create_all` en la app; todo cambio de modelo va con su migración Alembic (`tests/test_migrations.py` lo exige).
- Secretos: la app no arranca sin `JWT_SECRET` (≥ 32) y `FERNET_KEY` válidos; los tests desactivan el rate limit en `conftest.py`.
- Dependencias: versiones exactas y publicadas hace ≥ 2 semanas; CI falla con vulnerabilidades (pip-audit, npm audit high).
- Fechas y horas de auditoría en UTC desde un mismo instante (`utc_date_time()` en `app/utils/audit_columns.py`).
- No commitear `.env`, `.hypothesis/`, `.pytest_cache/`, `node_modules/`.
