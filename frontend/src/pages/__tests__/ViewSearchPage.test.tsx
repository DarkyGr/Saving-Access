import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

// Initialize i18n before importing the component so useTranslation() resolves
// real English strings instead of returning the raw key.
import "../../i18n/i18n";

// Mock apiClient before importing the page so the module under test picks up
// the mock on first import.
vi.mock("../../api/apiClient");

import ViewSearchPage from "../ViewSearchPage";
import apiClient from "../../api/apiClient";

// ── Fixture data ──────────────────────────────────────────────────────────────

const fixtureCredentials = [
  {
    credential_id: 1,
    website_name: "GitHub",
    email_or_username: "alice@example.com",
    is_username_login: false,
    password: null,
  },
  {
    credential_id: 2,
    website_name: "GitLab",
    email_or_username: "alice@gitlab.com",
    is_username_login: false,
    password: null,
  },
];

// ── Render helper ─────────────────────────────────────────────────────────────

function renderPage() {
  return render(
    <MemoryRouter>
      <ViewSearchPage />
    </MemoryRouter>
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("ViewSearchPage", () => {
  beforeEach(() => {
    // Default: every GET resolves with the fixture list
    vi.mocked(apiClient.get).mockResolvedValue({ data: fixtureCredentials });
    vi.mocked(apiClient.post).mockResolvedValue({ data: { password: "s3cr3t" } });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  // ── 1. Smoke test ────────────────────────────────────────────────────────

  it("renders the page title", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { name: /my credentials/i })
    ).toBeInTheDocument();
  });

  // ── 2. Password cells masked by default (Requirement 5.4) ────────────────

  it("password cells are masked by default (••••••••)", async () => {
    renderPage();

    // Wait for the credential rows to appear
    await screen.findByText("GitHub");

    // Every password cell must show the masked value, not any plaintext
    const maskedCells = screen.getAllByLabelText(/••••••••/i);
    expect(maskedCells.length).toBeGreaterThanOrEqual(1);

    // Extra safety: none of the visible text should be a leaked plaintext
    // (passwords are null in the fixture so none should appear as text)
    expect(screen.queryByText("s3cr3t")).not.toBeInTheDocument();
  });

  // ── 3. Search debounce calls correct API endpoint (Requirement 5.2) ──────

  it("search filters the loaded list, ignoring case and accents (Req 5.2, 13.4)", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
      url === "/api/credentials"
        ? {
            data: [
              ...fixtureCredentials,
              { credential_id: 3, website_name: "Banco Galicia", email_or_username: "josé", is_username_login: true, password: null },
            ],
          }
        : { data: { list_views: {} } }
    );
    renderPage();
    await screen.findByText("GitHub");
    // The list is loaded once; searching does not call the API again.
    const listCalls = () => vi.mocked(apiClient.get).mock.calls.filter(([url]) => url === "/api/credentials").length;
    expect(listCalls()).toBe(1);

    const search = screen.getByPlaceholderText(/search by website or email/i);
    await user.type(search, "GITL");
    expect(screen.getByText("GitLab")).toBeInTheDocument();
    expect(screen.queryByText("GitHub")).not.toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "jose");
    expect(screen.getByText("Banco Galicia")).toBeInTheDocument();
    expect(screen.queryByText("GitLab")).not.toBeInTheDocument();

    await user.clear(search);
    await user.type(search, "nothing-like-this");
    expect(screen.getByText("No credentials match the search or filters.")).toBeInTheDocument();
    expect(listCalls()).toBe(1);
  });

  it("filters by sign-in type", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
      url === "/api/credentials"
        ? {
            data: [
              ...fixtureCredentials,
              { credential_id: 3, website_name: "Steam", email_or_username: "gamer", is_username_login: true, password: null },
            ],
          }
        : { data: { list_views: {} } }
    );
    renderPage();
    await screen.findByText("Steam");
    await user.selectOptions(screen.getByLabelText("Sign-in"), "username");
    expect(screen.getByText("Steam")).toBeInTheDocument();
    expect(screen.queryByText("GitHub")).not.toBeInTheDocument();
  });

  it("says when there is nothing saved yet (not 'no results')", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
      url === "/api/credentials" ? { data: [] } : { data: { list_views: {} } }
    );
    renderPage();
    expect(await screen.findByText("You have not saved any credentials yet.")).toBeInTheDocument();
  });

  it("paginates 10 per page with the range and page size", async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 23 }, (_, i) => ({
      credential_id: i + 1,
      website_name: `Site ${String(i + 1).padStart(2, "0")}`,
      email_or_username: `u${i}@example.com`,
      is_username_login: false,
      password: null,
    }));
    vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
      url === "/api/credentials" ? { data: many } : { data: { list_views: {} } }
    );
    renderPage();
    expect(await screen.findByText("1–10 of 23")).toBeInTheDocument();
    expect(screen.getByText("Site 01")).toBeInTheDocument();
    expect(screen.queryByText("Site 11")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Last page" }));
    expect(screen.getByText("21–23 of 23")).toBeInTheDocument();
    expect(screen.getByText("Site 23")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Per page"), "50");
    expect(screen.getByText("1–23 of 23")).toBeInTheDocument();
  });

  it("switches to cards and saves the choice in the account", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
      url === "/api/credentials" ? { data: fixtureCredentials } : { data: { list_views: {} } }
    );
    vi.mocked(apiClient.put).mockResolvedValue({ data: { list_views: { credentials: "grid" } } });
    renderPage();
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Show as cards" }));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "GitHub" })).toBeInTheDocument();
    expect(apiClient.put).toHaveBeenCalledWith("/api/profile/preferences/list-view", {
      key: "credentials",
      view: "grid",
    });
  });

  it("opens in the view saved in the account", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
      url === "/api/credentials" ? { data: fixtureCredentials } : { data: { list_views: { credentials: "grid" } } }
    );
    renderPage();
    expect(await screen.findByRole("listitem", { name: "GitHub" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("table")).not.toBeInTheDocument());
  });

  // ── 4. Eye_Toggle opens PasswordConfirmModal (Requirements 5.5, 5.13) ────

  it("clicking Eye_Toggle opens PasswordConfirmModal", async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for rows
    await screen.findByText("GitHub");

    // Click the first "Show password" button
    const revealButtons = screen.getAllByRole("button", {
      name: /show password/i,
    });
    await user.click(revealButtons[0]);

    // Modal should now be visible
    expect(
      screen.getByRole("dialog", { name: /confirm your account password/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /confirm your account password/i })
    ).toBeInTheDocument();
  });

  // ── 5. Property 12 — PasswordConfirmModal always required (Req 5.13) ─────
  //
  // After cancelling the modal, clicking Eye_Toggle on the same row must
  // present the modal again — there is no session-level bypass.

  it("Property 12: PasswordConfirmModal always appears on Eye_Toggle click, even after cancelling once", async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for rows to load
    await screen.findByText("GitHub");

    const revealButtons = () =>
      screen.getAllByRole("button", { name: /show password/i });

    // ── First attempt ────────────────────────────────────────────────────
    await user.click(revealButtons()[0]);

    expect(
      screen.getByRole("dialog", { name: /confirm your account password/i })
    ).toBeInTheDocument();

    // Cancel the modal
    const cancelBtn = screen.getByRole("button", { name: /^cancel$/i });
    await user.click(cancelBtn);

    // Modal is gone
    expect(
      screen.queryByRole("dialog", { name: /confirm your account password/i })
    ).not.toBeInTheDocument();

    // ── Second attempt — modal must appear again ──────────────────────────
    await user.click(revealButtons()[0]);

    expect(
      screen.getByRole("dialog", { name: /confirm your account password/i })
    ).toBeInTheDocument();

    // Cancel again
    const cancelBtn2 = screen.getByRole("button", { name: /^cancel$/i });
    await user.click(cancelBtn2);

    expect(
      screen.queryByRole("dialog", { name: /confirm your account password/i })
    ).not.toBeInTheDocument();

    // ── Third attempt — still appears (confirms no session-level bypass) ──
    await user.click(revealButtons()[0]);

    expect(
      screen.getByRole("dialog", { name: /confirm your account password/i })
    ).toBeInTheDocument();
  });
});
