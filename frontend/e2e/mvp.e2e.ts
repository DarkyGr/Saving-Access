import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { createHmac } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

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

/**
 * Log in. Email verification is on in E2E (spec Phase 2): accounts created
 * through sign-up get the "verify your email" modal, which is closed here
 * unless the caller wants to inspect it.
 */
async function logIn(
  page: Page,
  username: string,
  { unverified = false, keepModal = false } = {}
) {
  await page.goto("/login");
  await page.getByPlaceholder("Enter your username").fill(username);
  await page.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  // Task 37.2: signing in opens Home.
  await expect(page).toHaveURL(/\/$/);
  const modal = page.getByRole("dialog", { name: "Verify your email" });
  if (!unverified) {
    await expect(modal).toHaveCount(0);
  } else if (!keepModal) {
    await modal.getByRole("button", { name: "Close" }).click();
    await expect(modal).toHaveCount(0);
  }
}

/** Sign out from the account menu (task 37.2). */
async function logOut(page: Page) {
  await page.getByRole("button", { name: /^Account menu of/ }).click();
  await page.getByRole("button", { name: "Log Out" }).click();
  // The session is revoked before the app shows the login page; a reload
  // before that could still find it.
  await expect(page).toHaveURL(/\/login$/);
}

/** Links to *route* emailed to *email*, oldest first (file email backend). */
function mailLinks(email: string, route: string): string[] {
  const dir = process.env.E2E_OUTBOX_DIR!;
  const pattern = new RegExp(String.raw`https?://\S+/${route}\?token=[\w-]+`);
  return readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => JSON.parse(readFileSync(path.join(dir, f), "utf-8")) as { to: string; body: string })
    .filter((m) => m.to === email)
    .flatMap((m) => pattern.exec(m.body)?.[0] ?? []);
}

/** Verification links sent to *email*, oldest first. */
function verificationLinks(email: string): string[] {
  return mailLinks(email, "verify-email");
}

async function confirmAccountPassword(page: Page, password = ACCOUNT_PW) {
  const dialog = page.getByRole("dialog");
  await dialog.getByPlaceholder("Your account password").fill(password);
  await dialog.getByRole("button", { name: "Confirm" }).click();
}

test("user lifecycle: sign up, log in, save, search, reveal, edit, delete, logout", async ({ page }) => {
  await signUp(page, user);

  // B1: login lands on /credentials instead of bouncing back to /login.
  // B2 + B5: a new sign-up is a User, whose role grants the vault (task 37.1).
  await logIn(page, user, { unverified: true });
  // Task 37.2: Home with an empty vault, then the grouped side menu.
  await expect(page.getByText("Your vault is empty.", { exact: false })).toBeVisible();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "My Credentials" }).click();
  await expect(page.getByRole("heading", { name: "My Credentials" })).toBeVisible();
  await expect(page.getByText("You have not saved any credentials yet.")).toBeVisible();

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

  // Search filters the list, ignoring case and accents (task 37.2).
  await page.getByPlaceholder(/Search by website/).fill("ÉNTERPRISE");
  const edited = page.getByRole("row", { name: /GitHub Enterprise/ });
  await expect(edited).toBeVisible();
  await expect(page.getByText("1–1 of 1")).toBeVisible();

  // Cards instead of the table, saved in the account: still cards after a reload.
  await page.getByRole("button", { name: "Show as cards" }).click();
  await expect(page.getByRole("listitem", { name: "GitHub Enterprise" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("listitem", { name: "GitHub Enterprise" })).toBeVisible();
  await page.getByRole("button", { name: "Show as a list" }).click();
  await page.getByPlaceholder(/Search by website/).fill("enterprise");

  // Home lists it as recently changed.
  await page.getByRole("link", { name: "Home" }).click();
  await expect(page.getByRole("region", { name: "Recently changed" })).toContainText("GitHub Enterprise");
  await page.getByRole("link", { name: "See all" }).click();
  await page.getByPlaceholder(/Search by website/).fill("enterprise");

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

  // Task 31.5: a full page reload keeps the session (httpOnly refresh cookie).
  await page.reload();
  await expect(page).toHaveURL(/\/credentials$/);
  await expect(page.getByTestId("current-user")).toHaveText(user);

  // Logout revokes the refresh cookie: a later reload cannot restore the session.
  await logOut(page);
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/credentials");
  await expect(page).toHaveURL(/\/login$/);
});

test("settings: profile, theme, private mode, start page, password and sessions", async ({ page, browser }) => {
  const name = `set_${run}`;
  const shots = process.env.E2E_SHOTS_DIR;
  const shot = async (file: string) => {
    if (shots) await page.screenshot({ path: path.join(shots, file), fullPage: true });
  };
  await signUp(page, name);
  await logIn(page, name, { unverified: true });

  // A second device, to see it in Active sessions and end it.
  const phone = await browser.newPage();
  await phone.goto("/login");
  await phone.getByPlaceholder("Enter your username").fill(name);
  await phone.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await phone.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(phone).toHaveURL(/\/$/);

  await page.getByRole("button", { name: /^Account menu of/ }).click();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByTestId("user-code")).toHaveText(/^SP-[2-9A-HJ-NP-Z]{6}$/);

  // Display name, avatar.
  await page.getByLabel("Display name", { exact: true }).fill("Ana Pérez");
  await page.getByRole("region", { name: "Profile" }).getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("region", { name: "Profile" }).getByRole("status")).toHaveText("Saved.");
  await page.getByRole("button", { name: "Rocket" }).click();
  await expect(page.getByRole("button", { name: "Rocket" })).toHaveAttribute("aria-pressed", "true");
  await shot("settings-light.png");

  // Dark theme and accent apply at once and survive a reload.
  await page.getByRole("radio", { name: "Dark" }).click();
  await page.getByRole("radio", { name: "Emerald" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator("html")).toHaveAttribute("data-accent", "emerald");
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await shot("settings-dark.png");

  // Start page.
  await page.getByLabel("Start page", { exact: true }).selectOption("credentials");
  await expect(page.getByRole("region", { name: "Preferences" }).getByRole("status")).toHaveText("Saved.");

  // Active sessions: end the phone's; it is signed out at once.
  const sessions = page.getByRole("region", { name: "Active sessions" });
  await expect(sessions.getByRole("listitem")).toHaveCount(2);
  await sessions.getByRole("button", { name: "End session" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "End session" }).click();
  await expect(sessions.getByRole("listitem")).toHaveCount(1);
  // Its refresh cookie no longer works: reopening the app asks to log in.
  await phone.goto("/credentials");
  await expect(phone).toHaveURL(/\/login$/);
  await phone.close();

  // Change the password.
  const passwordCard = page.getByRole("region", { name: "Password" });
  await passwordCard.getByLabel(/^Current password/).fill(ACCOUNT_PW);
  await passwordCard.getByLabel(/^New password/).fill("N3wStr0ngPass!");
  await passwordCard.getByLabel(/^Confirm the new password/).fill("N3wStr0ngPass!");
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByRole("region", { name: "Password" }).getByRole("status")).toContainText("Password changed.");

  // Private mode from the top bar hides emails in lists.
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Save Credential" }).click();
  await page.getByPlaceholder("e.g. github.com").fill("Notes");
  await page.getByPlaceholder("your@email.com").fill(`${name}@example.com`);
  await page.getByPlaceholder("Password for this website").fill("n0tes-secret");
  await page.getByRole("button", { name: "Save Credential" }).click();
  await confirmAccountPassword(page, "N3wStr0ngPass!");
  await expect(page.getByRole("row", { name: /Notes/ })).toContainText(`${name}@example.com`);
  await page.getByRole("button", { name: "Hide usernames and emails" }).click();
  await expect(page.getByRole("row", { name: /Notes/ })).not.toContainText(`${name}@example.com`);
  await shot("credentials-dark-private.png");

  // The new password and the start page apply at the next sign-in.
  await logOut(page);
  await page.getByPlaceholder("Enter your username").fill(name);
  await page.getByPlaceholder("Enter your password").fill("N3wStr0ngPass!");
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(page).toHaveURL(/\/credentials$/);
  await expect(page.getByTestId("current-user")).toHaveText(name);
});

test("admin: create via CLI, change a user's role, permissions follow", async ({ page }) => {
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

  // Task 37.1: no profiles any more, only the two roles.
  await logIn(page, admin);
  await expect(page.getByRole("link", { name: "Profiles" })).toHaveCount(0);
  await page.getByRole("link", { name: "Manage Users" }).click();
  await expect(page.getByLabel(`Change the role of ${admin}`)).toBeDisabled();

  // Promote the user from the first test.
  const role = page.getByLabel(`Change the role of ${user}`);
  await expect(role).toHaveValue("User");
  await role.selectOption("Admin");
  await expect(page.getByRole("status")).toHaveText("Role updated.");
  await logOut(page);

  // As Admin the user sees the administration.
  await logIn(page, user, { unverified: true });
  await page.getByRole("link", { name: "Manage Users" }).click();
  await expect(page.getByRole("heading", { name: "Manage Users" })).toBeVisible();
  await logOut(page);

  // Demote again.
  await logIn(page, admin);
  await page.getByRole("link", { name: "Manage Users" }).click();
  await page.getByLabel(`Change the role of ${user}`).selectOption("User");
  await expect(page.getByRole("status")).toHaveText("Role updated.");
  await logOut(page);

  // Back to User: vault yes, administration no.
  await logIn(page, user, { unverified: true });
  await expect(page.getByRole("link", { name: "Save Credential" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Manage Users" })).toHaveCount(0);
  // Client-side navigation: a full page.goto would reload and drop the
  // in-memory token, which would prove nothing about permissions.
  await page.evaluate(() => {
    window.history.pushState({}, "", "/admin/users");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page).toHaveURL(/\/403$/);
  await logOut(page);

  // Task 37.4: deactivate with a reason, the person cannot sign in, reactivate.
  await logIn(page, admin);
  await page.getByRole("link", { name: "Manage Users" }).click();
  await expect(page.getByLabel(`Deactivate ${admin}`)).toHaveCount(0);
  await page.getByLabel(`Deactivate ${user}`).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Reason (sent to the person)").fill("Testing the deactivation");
  await dialog.getByRole("button", { name: "Deactivate" }).click();
  await expect(page.getByRole("status")).toHaveText(`${user} was deactivated.`);
  await expect(page.getByText("Reason: Testing the deactivation")).toBeVisible();
  await logOut(page);

  await page.goto("/login");
  await page.getByPlaceholder("Enter your username").fill(user);
  await page.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("This account is deactivated");

  await logIn(page, admin);
  await page.getByRole("link", { name: "Manage Users" }).click();
  await page.getByLabel(`Reactivate ${user}`).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Reactivate" }).click();
  await expect(page.getByRole("status")).toHaveText(`${user} was reactivated.`);

  // The audit log shows it, newest first.
  await page.getByRole("link", { name: "Audit log" }).click();
  await expect(page.getByRole("heading", { name: "Audit log" })).toBeVisible();
  const rows = page.getByRole("row");
  await expect(rows.nth(1)).toContainText("Reactivated an account");
  await expect(page.getByRole("cell", { name: "Deactivated an account" })).toHaveCount(1);
  await page.getByLabel("Action").selectOption("user.role");
  await expect(page.getByRole("cell", { name: "Changed a role" })).toHaveCount(2);

  // Task 37.5: lock after 3 wrong passwords (System parameters), Admin unlocks.
  await page.getByRole("link", { name: "System parameters" }).click();
  const attempts = page.getByRole("spinbutton", { name: "Failed attempts before locking" });
  await attempts.fill("3");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Parameters saved.");
  await logOut(page);

  for (let i = 0; i < 3; i++) {
    await page.goto("/login");
    await page.getByPlaceholder("Enter your username").fill(user);
    await page.getByPlaceholder("Enter your password").fill("Wr0ngPassword!");
    await page.getByRole("button", { name: "Log In", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
  }
  await page.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("This account is locked");

  await logIn(page, admin);
  await page.getByRole("link", { name: "Manage Users" }).click();
  await page.getByLabel(`Unlock ${user}`).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByRole("status")).toHaveText(`${user} was unlocked.`);
  await page.getByRole("link", { name: "System parameters" }).click();
  await page.getByRole("spinbutton", { name: "Failed attempts before locking" }).fill("5");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Parameters saved.");
  await logOut(page);

  await logIn(page, user, { unverified: true });
});

function backend(args: string[]) {
  return execFileSync("python", args, {
    cwd: process.env.E2E_BACKEND_DIR,
    env: {
      ...process.env,
      DATABASE_URL: process.env.E2E_DATABASE_URL,
      FERNET_KEY: process.env.E2E_FERNET_KEY,
      JWT_SECRET: process.env.E2E_JWT_SECRET,
    },
  }).toString();
}

test("spec Phase 2: verify email, resend, deactivation and reactivation", async ({ page }) => {
  const name = `verify_${run}`;
  const email = `${name}@example.com`;

  // 1.9 / 1.10: sign-up mentions the email and sends one link.
  await signUp(page, name);
  await expect(page.getByRole("status")).toContainText("verify your address");
  await expect.poll(() => verificationLinks(email).length).toBe(1);

  // 2.7: the modal shows the deadline 30 days ahead; 2.8: resend sends a new link.
  await logIn(page, name, { unverified: true, keepModal: true });
  const modal = page.getByRole("dialog", { name: "Verify your email" });
  await expect(modal).toContainText("after that date the account will be deactivated");
  await modal.getByRole("button", { name: "Resend email" }).click();
  await expect(modal.getByRole("status")).toContainText("new verification email");
  await expect.poll(() => verificationLinks(email).length).toBe(2);
  await modal.getByRole("button", { name: "Close" }).click();
  await logOut(page);

  // 2.9: past the deadline and unverified → login refused with an explanation.
  backend([
    "-c",
    [
      "import datetime, os, sys",
      "from sqlalchemy import create_engine, text",
      "with create_engine(os.environ['DATABASE_URL']).begin() as c:",
      "    c.execute(text('UPDATE users SET deactivation_deadline = :d WHERE username = :u'),",
      "              {'d': datetime.date(2000, 1, 1), 'u': sys.argv[1]})",
    ].join("\n"),
    name,
  ]);
  await page.goto("/login");
  await page.getByPlaceholder("Enter your username").fill(name);
  await page.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("deactivated");
  await expect(page).toHaveURL(/\/login$/);

  // A link cannot reactivate it…
  await page.goto(verificationLinks(email)[1]);
  await expect(page.getByRole("alert")).toContainText("This account is deactivated");

  // …the admin CLI can.
  expect(backend(["-m", "app.cli", "verify-email", "--username", name])).toContain("verified");
  await logIn(page, name);
  await logOut(page);

  // 1.10: a fresh account verifies through the emailed link, once.
  const fresh = `fresh_${run}`;
  await signUp(page, fresh);
  await expect.poll(() => verificationLinks(`${fresh}@example.com`).length).toBe(1);
  const link = verificationLinks(`${fresh}@example.com`)[0];
  expect(link).toMatch(/^http:\/\/localhost:5174\/verify-email\?token=/);
  await page.goto(link);
  await expect(page.getByRole("alert")).toContainText("has been verified");
  await page.goto(link);
  await expect(page.getByRole("alert")).toContainText("already used");
  await logIn(page, fresh); // no modal any more
});

/** RFC 6238 code for *secret* (base32) at *time* (ms). */
function totpCode(secret: string, time = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/\s/g, "").toUpperCase()) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(time / 30000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

test("two-step verification: set up in Settings, sign in with a code and a recovery code", async ({ page }) => {
  test.setTimeout(120_000);
  const name = `totp_${run}`;
  await signUp(page, name);
  await logIn(page, name, { unverified: true });
  await page.getByRole("button", { name: /^Account menu of/ }).click();
  await page.getByRole("link", { name: "Settings" }).click();

  const card = page.getByRole("region", { name: "Two-step verification" });
  await expect(card).toContainText("Not set up yet.");
  await card.getByRole("button", { name: "Set up" }).click();
  await card.getByLabel("Current password *").fill(ACCOUNT_PW);
  await card.getByRole("button", { name: "Continue" }).click();
  await expect(card.getByRole("img", { name: /QR code/ })).toBeVisible();
  const secret = (await card.getByTestId("totp-secret").textContent()) ?? "";
  await card.getByLabel("6-digit code").fill(totpCode(secret));
  await card.getByRole("button", { name: "Confirm" }).click();
  const codes = card.getByRole("list", { name: "Save your recovery codes" }).getByRole("listitem");
  await expect(codes).toHaveCount(10);
  const recovery = (await codes.first().textContent()) ?? "";
  await card.getByLabel("I saved my recovery codes").check();
  await card.getByRole("button", { name: "Done" }).click();
  await expect(card).toContainText("10 recovery codes left.");
  await logOut(page);

  // A code is accepted once: wait for the next 30-second step.
  await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 1_000);
  await page.goto("/login");
  await page.getByPlaceholder("Enter your username").fill(name);
  await page.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await page.getByLabel("6-digit code").fill(totpCode(secret));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole("dialog", { name: "Verify your email" }).getByRole("button", { name: "Close" }).click();
  await logOut(page);

  await page.goto("/login");
  await page.getByPlaceholder("Enter your username").fill(name);
  await page.getByPlaceholder("Enter your password").fill(ACCOUNT_PW);
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await page.getByRole("button", { name: "Use a recovery code" }).click();
  await page.getByLabel("Recovery code").fill(recovery);
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("forgot password: emailed link, new password, sign in", async ({ page }) => {
  const name = `reset_${run}`;
  const email = `${name}@example.com`;
  await signUp(page, name);
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await page.getByLabel("Username or email").fill(email.toUpperCase());
  await page.getByRole("button", { name: "Email me a link" }).click();
  await expect(page.getByRole("status")).toContainText("If that account exists");
  await expect.poll(() => mailLinks(email, "reset-password").length).toBe(1);

  await page.goto(mailLinks(email, "reset-password")[0].replace(/^https?:\/\/[^/]+/, ""));
  await page.getByLabel("New password *", { exact: true }).fill("N3wStr0ngPass!");
  await page.getByLabel("Confirm the new password *", { exact: true }).fill("N3wStr0ngPass!");
  await page.getByRole("button", { name: "Save the new password" }).click();
  await expect(page.getByRole("status")).toContainText("Your password was changed");

  await page.goto("/login");
  await page.getByPlaceholder("Enter your username").fill(name);
  await page.getByPlaceholder("Enter your password").fill("N3wStr0ngPass!");
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);

  // Task 35.7: save a credential with a generated password, then reveal it.
  await page.getByRole("dialog", { name: "Verify your email" }).getByRole("button", { name: "Close" }).click();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Save Credential" }).click();
  await page.getByPlaceholder("e.g. github.com").fill("Generated");
  await page.getByPlaceholder("your@email.com").fill(email);
  await page.getByRole("button", { name: "Generate a strong password" }).click();
  await expect(page.getByTestId("generated-password")).toHaveText(/^\S{20}$/);
  const generated = (await page.getByTestId("generated-password").textContent()) ?? "";
  await page.getByRole("button", { name: "Use this password" }).click();
  await expect(page.getByPlaceholder("Password for this website")).toHaveValue(generated);
  await page.getByRole("button", { name: "Save Credential" }).click();
  await confirmAccountPassword(page, "N3wStr0ngPass!");
  const row = page.getByRole("row", { name: /Generated/ });
  await row.getByRole("button", { name: "Show password" }).click();
  await confirmAccountPassword(page, "N3wStr0ngPass!");
  await expect(row.getByText(generated, { exact: true })).toBeVisible();

  // Task 35.8: export my passwords, then delete the account.
  await page.getByRole("button", { name: /^Account menu of/ }).click();
  await page.getByRole("link", { name: "Settings" }).click();
  const data = page.getByRole("region", { name: "Your data" });
  await data.locator("#export-password").fill("N3wStr0ngPass!");
  const [download] = await Promise.all([page.waitForEvent("download"), data.getByRole("button", { name: "Download" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^save-pass-export-\d{8}\.csv$/);
  const csvText = readFileSync((await download.path())!, "utf-8");
  expect(csvText).toContain(generated);

  await data.locator("#delete-password").fill("N3wStr0ngPass!");
  await data.getByLabel(/Type your username/).fill(name);
  await data.getByRole("button", { name: "Delete my account" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("status")).toContainText("Your account and its passwords were deleted.");
  await page.getByPlaceholder("Enter your username").fill(name);
  await page.getByPlaceholder("Enter your password").fill("N3wStr0ngPass!");
  await page.getByRole("button", { name: "Log In", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid");
});

