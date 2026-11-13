import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";

/**
 * Phase 1 acceptance test: the whole MVP works against the real backend.
 * Covers blockers B1–B7 from the Kiro → Claude Code audit.
 */

const ACCOUNT_PW = "Str0ngPassw0rd!";
const run = Date.now().toString(36);
const user = `user_${run}`;
const admin = `admin_${run}`;

async function signUp(page: Page, username: string) {
  await page.goto("/signup");
  await page.getByPlaceholder("Choose a username").fill(username);
  await page.getByPlaceholder("Enter your email address").fill(`${username}@example.com`);
  await page.getByPlaceholder("Create a password").fill(ACCOUNT_PW);
  await page.getByPlaceholder("Re-enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Create Account" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

async function logIn(page: Page, username: string) {
  await page.goto("/login");
  await page.getByPlaceholder("Enter your username").fill(username);
  await page.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(page).toHaveURL(/\/credentials$/);
}

async function confirmAccountPassword(page: Page, password = ACCOUNT_PW) {
  const dialog = page.getByRole("dialog");
  await dialog.getByPlaceholder("Your account password").fill(password);
  await dialog.getByRole("button", { name: "Confirm" }).click();
}

test("user lifecycle: sign up, log in, save, search, reveal, edit, delete, logout", async ({ page }) => {
  await signUp(page, user);

  // B1: login lands on /credentials instead of bouncing back to /login.
  // B2 + B5: the new user has a default profile, so ProtectedRoute lets them in.
  await logIn(page, user);
  await expect(page.getByRole("heading", { name: "My Credentials" })).toBeVisible();

  // B7: header with user, language toggle and logout.
  await expect(page.getByTestId("current-user")).toHaveText(user);
  await expect(page.getByRole("link", { name: "Save Credential" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Manage Users" })).toHaveCount(0);

  // Save a credential.
  await page.getByRole("link", { name: "Save Credential" }).click();
  await page.getByPlaceholder("e.g. github.com").fill("GitHub");
  await page.getByPlaceholder("your@email.com").fill(`${user}@example.com`);
  await page.getByPlaceholder("Password for this website").fill("gh-secret-123");
  await page.getByRole("button", { name: "Save Credential" }).click();
  await confirmAccountPassword(page);
  await expect(page).toHaveURL(/\/credentials$/);
  const row = page.getByRole("row", { name: /GitHub/ });
  await expect(row).toBeVisible();

  // B6: a wrong account password shows an inline error and keeps the session.
  await row.getByRole("button", { name: "Show password" }).click();
  await confirmAccountPassword(page, "wrong-password");
  await expect(page.getByRole("dialog").getByText("Incorrect account password.")).toBeVisible();
  await expect(page).toHaveURL(/\/credentials$/);

  // Correct password reveals the plaintext.
  await confirmAccountPassword(page);
  await expect(row.getByText("gh-secret-123")).toBeVisible();
  await row.getByRole("button", { name: "Hide password" }).click();
  await expect(row.getByText("gh-secret-123")).toHaveCount(0);

  // B3: the edit page loads the credential from GET /api/credentials/:id.
  await row.getByRole("link", { name: "Edit GitHub" }).click();
  const website = page.getByPlaceholder("e.g. github.com");
  await expect(website).toHaveValue("GitHub");
  await website.fill("GitHub Enterprise");
  await page.getByPlaceholder("Leave unchanged or enter a new password").fill("gh-secret-456");
  await page.getByRole("button", { name: "Update Credential" }).click();
  await confirmAccountPassword(page);
  await expect(page).toHaveURL(/\/credentials$/);

  // Search filters the list.
  await page.getByPlaceholder(/Search by website/).fill("enterprise");
  const edited = page.getByRole("row", { name: /GitHub Enterprise/ });
  await expect(edited).toBeVisible();

  // Delete.
  await edited.getByRole("button", { name: "Delete GitHub Enterprise" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();
  await confirmAccountPassword(page);
  await expect(page.getByRole("row", { name: /GitHub Enterprise/ })).toHaveCount(0);

  // Language toggle switches without reload (Req 10.3).
  await page.getByRole("button", { name: "Spanish" }).click();
  await expect(page.getByRole("heading", { name: "Mis Credenciales" })).toBeVisible();
  await page.getByRole("button", { name: "Inglés" }).or(page.getByRole("button", { name: "English" })).click();
  await expect(page.getByRole("heading", { name: "My Credentials" })).toBeVisible();

  // Logout returns to login and protected pages are closed again.
  await page.getByRole("button", { name: "Log Out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/credentials");
  await expect(page).toHaveURL(/\/login$/);
});

test("admin: create via CLI, see admin pages, reassign a user's profile", async ({ page }) => {
  // B5: the first Admin is created with the backend CLI.
  execFileSync(
    "python",
    ["-m", "app.cli", "create-admin", "--username", admin, "--email", `${admin}@example.com`],
    {
      cwd: process.env.E2E_BACKEND_DIR,
      env: {
        ...process.env,
        DATABASE_URL: process.env.E2E_DATABASE_URL,
        FERNET_KEY: process.env.E2E_FERNET_KEY,
        JWT_SECRET: process.env.E2E_JWT_SECRET,
        BCRYPT_ROUNDS: "4",
        ADMIN_PASSWORD: ACCOUNT_PW,
      },
    }
  );

  await logIn(page, admin);

  // B4: profiles come from GET /api/admin/profiles, not hard-coded data.
  await page.getByRole("link", { name: "Profiles" }).click();
  await expect(page.getByText("Basic", { exact: true })).toBeVisible();
  await expect(page.getByText("Full", { exact: true })).toBeVisible();

  // Reassign the user from the first test to the read-only "Basic" profile.
  await page.getByRole("link", { name: "Manage Users" }).click();
  const userRow = page.getByRole("row", { name: new RegExp(user) });
  await expect(userRow).toBeVisible();
  await userRow.getByRole("combobox").selectOption({ label: "Basic" });
  await expect(page.getByText("Profile assigned successfully.")).toBeVisible();

  await page.getByRole("button", { name: "Log Out" }).click();

  // The user now only sees the list screen; /credentials/new is forbidden.
  await logIn(page, user);
  await expect(page.getByRole("link", { name: "Save Credential" })).toHaveCount(0);
  // Client-side navigation: a full page.goto would reload and drop the
  // in-memory token, which would prove nothing about permissions.
  await page.evaluate(() => {
    window.history.pushState({}, "", "/credentials/new");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page).toHaveURL(/\/403$/);
});
