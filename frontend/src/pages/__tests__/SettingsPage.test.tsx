import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { useEffect } from "react";
import "../../i18n/i18n";
import i18n from "../../i18n/i18n";
import SettingsPage from "../SettingsPage";
import ViewSearchPage from "../ViewSearchPage";
import { AuthProvider, useAuth } from "../../context/AuthContext";
import { PreferencesProvider, type Me, type Preferences } from "../../context/PreferencesContext";
import apiClient from "../../api/apiClient";
import { httpError } from "../../test/axiosError";
import { describeDevice } from "../../lib/device";

function makeJwt(payload: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${enc({ alg: "HS256", typ: "JWT" })}.${enc(payload)}.sig`;
}
const token = makeJwt({ user_id: 7, username: "alice", role: "User", exp: 9999999999 });

const PREFS: Preferences = {
  list_views: {},
  theme: "light",
  accent: "indigo",
  start_page: "home",
  private_mode: false,
  language: "en",
  avatar_preset: null,
  has_avatar_image: false,
};
const ME: Me = {
  user_id: 7,
  user_code: "SP-7K3M9Q",
  username: "alice",
  display_name: null,
  email: "alice@example.com",
  role: "User",
  email_verified: true,
  preferences: PREFS,
};
const SESSIONS = [
  {
    session_id: "a".repeat(32),
    user_agent: "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
    client_ip: "127.0.0.1",
    started: "2026-11-16T10:00:00Z",
    last_active: "2026-11-16T12:00:00Z",
    current: true,
  },
  {
    session_id: "b".repeat(32),
    user_agent: "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
    client_ip: "192.168.1.20",
    started: "2026-11-15T10:00:00Z",
    last_active: "2026-11-15T11:00:00Z",
    current: false,
  },
];

function SignedIn({ children }: { children: React.ReactNode }) {
  const { login, user } = useAuth();
  useEffect(() => login(token), [login]);
  return user ? <>{children}</> : null;
}

function renderWith(ui: React.ReactNode) {
  return render(
    <AuthProvider>
      <PreferencesProvider>
        <MemoryRouter>
          <SignedIn>{ui}</SignedIn>
        </MemoryRouter>
      </PreferencesProvider>
    </AuthProvider>
  );
}

function mockApi(overrides: Partial<Me["preferences"]> = {}) {
  const prefs = { ...PREFS, ...overrides };
  vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
    if (url === "/api/profile/me") return { data: { ...ME, preferences: prefs } };
    if (url === "/api/profile/permissions") return { data: { permissions: ["credentials.view", "credentials.create"] } };
    if (url === "/api/profile/sessions") return { data: SESSIONS };
    if (url === "/api/profile/preferences") return { data: prefs };
    if (url === "/api/credentials")
      return { data: [{ credential_id: 1, website_name: "GitHub", email_or_username: "alice@example.com", is_username_login: false, password: null }] };
    throw new Error(`unexpected GET ${url}`);
  });
  return prefs;
}

describe("SettingsPage (task 37.3)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    document.documentElement.className = "";
    delete document.documentElement.dataset.accent;
    window.localStorage.clear();
    void i18n.changeLanguage("en");
  });

  it("shows the account with its immutable user ID and saves the display name", async () => {
    const user = userEvent.setup();
    mockApi();
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: { ...ME, display_name: "Alicia" } });
    renderWith(<SettingsPage />);
    expect(await screen.findByTestId("user-code")).toHaveTextContent("SP-7K3M9Q");
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();

    const name = screen.getByLabelText("Display name", { selector: "input" });
    await user.type(name, "<b>");
    await user.click(within(screen.getByRole("region", { name: "Profile" })).getByRole("button", { name: "Save" }));
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(put).not.toHaveBeenCalled();

    await user.clear(name);
    await user.type(name, "Alicia");
    await user.click(within(screen.getByRole("region", { name: "Profile" })).getByRole("button", { name: "Save" }));
    expect(put).toHaveBeenCalledWith("/api/profile/me", { display_name: "Alicia" });
    expect(await screen.findAllByText("Alicia")).not.toHaveLength(0);
  });

  it("applies the theme and the accent at once and saves them", async () => {
    const user = userEvent.setup();
    mockApi();
    const put = vi.spyOn(apiClient, "put").mockImplementation(async (_url, body) => ({ data: { ...PREFS, ...(body as object) } }));
    renderWith(<SettingsPage />);
    await user.click(await screen.findByRole("radio", { name: "Dark" }));
    expect(document.documentElement).toHaveClass("dark");
    expect(put).toHaveBeenCalledWith("/api/profile/preferences", { theme: "dark" });
    expect(JSON.parse(window.localStorage.getItem("savepass-theme")!)).toBe("dark");

    await user.click(screen.getByRole("radio", { name: "Rose" }));
    expect(document.documentElement.dataset.accent).toBe("rose");
    await user.click(screen.getByRole("radio", { name: "Light" }));
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("offers only start pages the role can open", async () => {
    mockApi();
    renderWith(<SettingsPage />);
    const select = await screen.findByLabelText("Start page", { selector: "select" });
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(3));
  });

  it("checks the password rules before sending and reports a wrong current password", async () => {
    const user = userEvent.setup();
    mockApi();
    const post = vi.spyOn(apiClient, "post");
    renderWith(<SettingsPage />);
    const card = await screen.findByRole("region", { name: "Password" });
    await user.click(within(card).getByRole("button", { name: "Change password" }));
    expect(post).not.toHaveBeenCalled();
    expect(within(card).getByLabelText(/Current password/, { selector: "input" })).toHaveFocus();

    post.mockRejectedValueOnce(httpError(401, "Account password verification failed."));
    await user.type(within(card).getByLabelText(/Current password/, { selector: "input" }), "wrong");
    await user.type(within(card).getByLabelText(/^New password/, { selector: "input" }), "N3wStr0ngPass!");
    await user.type(within(card).getByLabelText(/Confirm the new password/, { selector: "input" }), "N3wStr0ngPass!");
    await user.click(within(card).getByRole("button", { name: "Change password" }));
    expect(await within(card).findByText("Incorrect account password.")).toBeInTheDocument();

    post.mockResolvedValueOnce({ status: 204, data: undefined });
    await user.clear(within(card).getByLabelText(/Current password/, { selector: "input" }));
    await user.type(within(card).getByLabelText(/Current password/, { selector: "input" }), "Str0ngPassw0rd!");
    await user.click(within(card).getByRole("button", { name: "Change password" }));
    expect(await within(card).findByRole("status")).toHaveTextContent("Password changed.");
    expect(post).toHaveBeenLastCalledWith("/api/profile/password", {
      current_password: "Str0ngPassw0rd!",
      new_password: "N3wStr0ngPass!",
      new_password_confirmation: "N3wStr0ngPass!",
    });
  });

  it("lists the sessions and ends another device after confirming", async () => {
    const user = userEvent.setup();
    mockApi();
    const del = vi.spyOn(apiClient, "delete").mockResolvedValue({ status: 204, data: undefined });
    renderWith(<SettingsPage />);
    const card = await screen.findByRole("region", { name: "Active sessions" });
    expect(await within(card).findByText(/Chrome · Windows/)).toBeInTheDocument();
    expect(within(card).getByText("This device")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "End session" }));
    const dialog = screen.getByRole("alertdialog", { name: "End this session?" });
    await user.click(within(dialog).getByRole("button", { name: "End session" }));
    expect(del).toHaveBeenCalledWith(`/api/profile/sessions/${"b".repeat(32)}`);
  });
});

describe("Private mode (Requirement 14.3)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("hides usernames and emails in the credentials list", async () => {
    mockApi({ private_mode: true });
    renderWith(<ViewSearchPage />);
    expect(await screen.findByText("GitHub")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("alice@example.com")).not.toBeInTheDocument());
    expect(screen.getAllByText("••••••••").length).toBeGreaterThan(0);
  });
});

describe("describeDevice", () => {
  it("names browser and system", () => {
    expect(describeDevice(SESSIONS[1].user_agent)).toEqual({ browser: "Chrome", os: "Android" });
    expect(describeDevice("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Version/17.0 Mobile Safari/604.1")).toEqual({ browser: "Safari", os: "iOS" });
    expect(describeDevice("Mozilla/5.0 (Windows NT 10.0) Chrome/131.0 Edg/131.0")).toEqual({ browser: "Edge", os: "Windows" });
    expect(describeDevice(null)).toEqual({ browser: null, os: null });
  });
});
