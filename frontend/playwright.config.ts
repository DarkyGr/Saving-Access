import { defineConfig, devices } from "@playwright/test";
import { randomBytes } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * End-to-end tests against the real backend + frontend (no mocks).
 *
 * Playwright starts:
 *  - FastAPI (uvicorn) on :8001 with a throwaway SQLite file DB
 *  - Vite dev server on :5174 pointed at that backend
 *
 * Ports differ from `make up` (8000 / 5173) so both can run side by side.
 */

const here = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(here, "../backend");
const dbFile = path.join(backendDir, "e2e.sqlite3");

const API_PORT = 8001;
const WEB_PORT = 5174;

// Generated once in the main process and inherited by workers via env so the
// backend and the tests (which call the admin CLI) share the same values.
process.env.E2E_FERNET_KEY ??= randomBytes(32).toString("base64url") + "=";
process.env.E2E_JWT_SECRET ??= randomBytes(32).toString("hex");
process.env.E2E_DATABASE_URL = `sqlite:///${dbFile.replace(/\\/g, "/")}`;
process.env.E2E_BACKEND_DIR = backendDir;

const backendEnv = {
  DATABASE_URL: process.env.E2E_DATABASE_URL,
  FERNET_KEY: process.env.E2E_FERNET_KEY,
  JWT_SECRET: process.env.E2E_JWT_SECRET,
  JWT_ALGORITHM: "HS256",
  JWT_EXPIRE_MINUTES: "15",
  BCRYPT_ROUNDS: "4",
  CORS_ORIGINS: `http://localhost:${WEB_PORT}`,
  ENVIRONMENT: "e2e",
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Fresh DB every run: migrations create the schema, startup seeds profiles.
      command:
        `python -c "import pathlib; pathlib.Path(r'${dbFile}').unlink(missing_ok=True)" && ` +
        `python -m alembic upgrade head && ` +
        `python -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://localhost:${API_PORT}/docs`,
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      cwd: here,
      url: `http://localhost:${WEB_PORT}`,
      env: { VITE_API_URL: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
