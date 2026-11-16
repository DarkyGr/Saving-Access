import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { useEffect } from "react";
import "../../i18n/i18n";
import AppLayout from "../AppLayout";
import { AuthProvider, useAuth } from "../../context/AuthContext";
import apiClient from "../../api/apiClient";

function makeJwt(payload: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${enc({ alg: "HS256", typ: "JWT" })}.${enc(payload)}.sig`;
}

const adminToken = makeJwt({ user_id: 1, username: "root", role: "Admin", exp: 9999999999 });
const ALL = ["credentials.view", "credentials.create", "credentials.edit", "credentials.delete", "credentials.reveal", "users.manage"];

function LoginAs({ token }: { token: string }) {
  const { login } = useAuth();
  useEffect(() => login(token), [token, login]);
  return <p>page body</p>;
}

function renderAt(path: string, permissions: string[]) {
  vi.spyOn(apiClient, "get").mockResolvedValue({ data: { permissions } });
  const router = createMemoryRouter(
    [
      {
        element: <AppLayout />,
        children: ["/", "/credentials", "/credentials/new", "/admin/users"].map((p) => ({
          path: p,
          element: <LoginAs token={adminToken} />,
        })),
      },
    ],
    { initialEntries: [path] }
  );
  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
  return router;
}

describe("Application shell (task 37.2)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("groups the menu and hides groups without visible entries", async () => {
    renderAt("/", ["credentials.view", "credentials.create"]);
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(await within(nav).findByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
    expect(within(nav).getByRole("button", { name: "Vault" })).toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: "Administration" })).not.toBeInTheDocument();
    // Task 37.6: everyone gets the user guide; the technical guide is the Admin's.
    expect(within(nav).getByRole("button", { name: "Help" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "User guide" })).toHaveAttribute("href", "/help");
    expect(within(nav).queryByRole("link", { name: "Technical guide" })).not.toBeInTheDocument();
  });

  it("closes a group by its title, remembers it, and keeps the current group open", async () => {
    const user = userEvent.setup();
    renderAt("/admin/users", ALL);
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    const vault = await within(nav).findByRole("button", { name: "Vault" });
    await user.click(vault);
    expect(vault).toHaveAttribute("aria-expanded", "false");
    expect(within(nav).queryByRole("link", { name: "My Credentials" })).not.toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem("savepass-nav-closed")!)).toEqual(["vault"]);

    const admin = within(nav).getByRole("button", { name: "Administration" });
    expect(admin).toBeDisabled();
    expect(admin).toHaveAttribute("title", expect.stringContaining("screen you are on"));
    expect(within(nav).getByRole("link", { name: "Manage Users" })).toBeInTheDocument();
  });

  it("collapses the side menu to icons and remembers it on this device", async () => {
    const user = userEvent.setup();
    renderAt("/credentials", ALL);
    await user.click(await screen.findByRole("button", { name: "Collapse the menu to icons" }));
    expect(screen.getByRole("button", { name: "Expand the menu" })).toBeInTheDocument();
    expect(window.localStorage.getItem("savepass-sidebar-collapsed")).toBe("true");
    // Icon links keep their names for screen readers and tooltips.
    expect(screen.getAllByRole("link", { name: "My Credentials" })[0]).toHaveAttribute("title", "My Credentials");
  });

  it("opens the phone drawer and closes it after choosing a screen", async () => {
    const user = userEvent.setup();
    const router = renderAt("/", ALL);
    await user.click(await screen.findByRole("button", { name: "Open the menu" }));
    const drawer = screen.getByRole("dialog", { name: "Menu" });
    await user.click(await within(drawer).findByRole("link", { name: "Save Credential" }));
    expect(router.state.location.pathname).toBe("/credentials/new");
    expect(screen.queryByRole("dialog", { name: "Menu" })).not.toBeInTheDocument();
  });

  it("account menu shows the user and the role, and closes with Escape", async () => {
    const user = userEvent.setup();
    renderAt("/", ALL);
    const button = await screen.findByRole("button", { name: "Account menu of root" });
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Admin", { selector: "p" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });
});
