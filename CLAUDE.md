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
- Docker Compose: `db`, `backend` (:8000), `frontend` (:5173)

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

# todo
make up / make down / make test-backend / make test-frontend
```

## Convenciones

- Commits: Conventional Commits (`feat(frontend): …`, `fix(backend): …`, `test: …`, `docs(tasks): …`).
- Toda operación sensible (save/reveal/edit/delete) re-verifica la contraseña de cuenta y escribe en `audit_log`.
- El JWT vive solo en memoria (nunca localStorage/cookies legibles por JS).
- Todo texto de UI va por `t()`; cualquier clave nueva se añade a `en.json` y `es.json`.
- Contratos de API: si el frontend llama a un endpoint, el backend debe tenerlo registrado y con test de integración.
- Esquema: nunca `create_all` en la app; todo cambio de modelo va con su migración Alembic (`tests/test_migrations.py` lo exige).
- Secretos: la app no arranca sin `JWT_SECRET` (≥ 32) y `FERNET_KEY` válidos; los tests desactivan el rate limit en `conftest.py`.
- No commitear `.env`, `.hypothesis/`, `.pytest_cache/`, `node_modules/`.
