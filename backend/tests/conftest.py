"""
Shared pytest configuration.

Several test modules configure their own in-memory SQLite engine and register
``app.dependency_overrides[get_db]`` (plus JWT / Fernet env vars) at import
time.  When pytest collects the whole suite, every module is imported before
any test runs, so the *last* imported module's override wins for everyone and
earlier modules end up talking to a database that does not contain their data.

This autouse fixture re-applies the importing module's own override and env
vars before that module's tests run, so each module is isolated regardless of
collection order.
"""

import os

# Rate limiting would make the Hypothesis suites (hundreds of logins) fail
# with 429; tests that cover limits re-enable the limiter explicitly.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")



import pytest


@pytest.fixture(autouse=True, scope="module")
def _activate_module_db_override(request):
    module = request.module
    override = getattr(module, "_override_get_db", None)
    if override is None:
        yield
        return

    from app.database import get_db
    from app.main import app

    env_backup = {k: os.environ.get(k) for k in ("JWT_SECRET", "JWT_ALGORITHM", "FERNET_KEY")}
    if hasattr(module, "_TEST_JWT_SECRET"):
        os.environ["JWT_SECRET"] = module._TEST_JWT_SECRET
    if hasattr(module, "_TEST_JWT_ALGORITHM"):
        os.environ["JWT_ALGORITHM"] = module._TEST_JWT_ALGORITHM
    if hasattr(module, "_TEST_FERNET_KEY"):
        os.environ["FERNET_KEY"] = module._TEST_FERNET_KEY

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
