import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

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

  it("typing 'git' in the search box triggers GET /api/credentials?q=git after debounce", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    renderPage();

    // Initial load call (empty query) must complete first
    await vi.runAllTimersAsync();
    await waitFor(() => expect(vi.mocked(apiClient.get)).toHaveBeenCalledTimes(1));
    vi.clearAllMocks();

    // Mock the search response
    vi.mocked(apiClient.get).mockResolvedValue({ data: fixtureCredentials });

    const searchInput = screen.getByPlaceholderText(
      /search by website or email/i
    );
    await user.type(searchInput, "git");

    // Advance past the 300 ms debounce
    vi.advanceTimersByTime(300);
    await vi.runAllTimersAsync();

    await waitFor(() =>
      expect(vi.mocked(apiClient.get)).toHaveBeenCalledWith(
        "/api/credentials",
        expect.objectContaining({ params: { q: "git" } })
      )
    );
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
