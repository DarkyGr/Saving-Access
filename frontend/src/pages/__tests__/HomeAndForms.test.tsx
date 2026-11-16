import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import "../../i18n/i18n";
import HomePage from "../HomePage";
import SaveCredentialPage from "../SaveCredentialPage";
import { AuthProvider } from "../../context/AuthContext";
import apiClient from "../../api/apiClient";
import { fold, matchesQuery } from "../../lib/text";

describe("text search helpers", () => {
  it("ignores case and accents", () => {
    expect(fold("ÁrBol Niño")).toBe("arbol nino");
    expect(matchesQuery("arbol", ["Árbol"])).toBe(true);
    expect(matchesQuery("git hub", ["GitHub", "hub@x.com"])).toBe(true);
    expect(matchesQuery("gitlab", ["GitHub"])).toBe(false);
    expect(matchesQuery("   ", ["anything"])).toBe(true);
  });
});

describe("HomePage (Requirement 13.3)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("counts the credentials and lists the most recently changed first", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [
        { credential_id: 1, website_name: "Old", email_or_username: "a@x.com", is_username_login: false, password: null, last_changed: "2026-01-01T10:00:00Z" },
        { credential_id: 2, website_name: "Newest", email_or_username: "neo", is_username_login: true, password: null, last_changed: "2026-11-15T10:00:00Z" },
        { credential_id: 3, website_name: "Middle", email_or_username: "m@x.com", is_username_login: false, password: null, last_changed: "2026-06-01T10:00:00Z" },
      ],
    });
    render(
      <AuthProvider>
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </AuthProvider>
    );
    const recent = await screen.findByRole("region", { name: "Recently changed" });
    const names = within(recent).getAllByRole("listitem").map((li) => li.querySelector("p")!.textContent);
    expect(names).toEqual(["Newest", "Middle", "Old"]);
    expect(screen.getByText("Saved credentials").nextSibling).toHaveTextContent("3");
    expect(screen.getByText("Sign in with a username").nextSibling).toHaveTextContent("1");
    expect(screen.getByRole("link", { name: "See all" })).toHaveAttribute("href", "/credentials");
  });

  it("invites to save the first credential when the vault is empty", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    render(
      <AuthProvider>
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </AuthProvider>
    );
    expect(await screen.findByText(/Your vault is empty/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Save New Credential" })).toHaveAttribute("href", "/credentials/new");
  });
});

describe("Form patterns (Requirement 13.5)", () => {
  it("marks invalid fields, focuses the first one and says what is wrong", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SaveCredentialPage />
      </MemoryRouter>
    );
    await user.type(screen.getByLabelText(/Website Name/, { selector: "input" }), "-bad");
    await user.click(screen.getByRole("button", { name: "Save Credential" }));

    const website = screen.getByLabelText(/Website Name/, { selector: "input" });
    expect(website).toHaveAttribute("aria-invalid", "true");
    expect(website).toHaveFocus();
    expect(screen.getByText("Start with a letter or a number.")).toBeInTheDocument();
    expect(screen.getAllByText("This field is required.").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Typing clears that field's error without moving the focus.
    await user.type(website, "x");
    expect(website).toHaveFocus();
  });

  it("shows field help in a tooltip", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SaveCredentialPage />
      </MemoryRouter>
    );
    const help = screen.getByRole("button", { name: /Help: Website Name/ });
    await user.click(help);
    expect(screen.getByRole("tooltip")).toHaveTextContent("for example github.com");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
