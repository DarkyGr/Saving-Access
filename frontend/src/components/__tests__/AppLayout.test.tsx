import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
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

// Logs in with the given token once mounted (simulates LoginPage success).
function LoginAs({ token }: { token: string | null }) {
  const { login } = useAuth();
  useEffect(() => {
    if (token) login(token);
  }, [token, login]);
  return <p>page body</p>;
}

function renderLayout(token: string | null) {
  const router = createMemoryRouter(
    [
      {
        element: <AppLayout />,
        children: [
          { path: "/credentials", element: <LoginAs token={token} /> },
          { path: "/login", element: <p>login page</p> },
        ],
      },
    ],
    { initialEntries: ["/credentials"] }
  );
  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
  return router;
}

const userToken = makeJwt({ user_id: 2, username: "alice", role: "User", exp: 9999999999 });
const adminToken = makeJwt({ user_id: 1, username: "root", role: "Admin", exp: 9999999999 });

describe("AppLayout", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the language toggle even when logged out (Req 10.2)", () => {
    renderLayout(null);
    expect(screen.getByRole("group", { name: /language/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("shows only the screens the user's permissions allow", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { permissions: ["credentials.view"] } });
    renderLayout(userToken);
    expect(await screen.findByRole("link", { name: "My Credentials" })).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledWith("/api/profile/permissions");
    expect(screen.queryByRole("link", { name: "Save Credential" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Manage Users" })).not.toBeInTheDocument();
    expect(screen.getByTestId("current-user")).toHaveTextContent("alice");
  });

  it("asks the API for an Admin too and shows what it grants (no bypass)", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { permissions: ["credentials.view", "credentials.create", "users.manage"] },
    });
    renderLayout(adminToken);
    expect(await screen.findByRole("link", { name: "Manage Users" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Save Credential" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Profiles" })).not.toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/api/profile/permissions");
  });

  it("hides the admin link from an Admin token the API no longer grants", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { permissions: ["credentials.view"] } });
    renderLayout(adminToken);
    expect(await screen.findByRole("link", { name: "My Credentials" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Manage Users" })).not.toBeInTheDocument();
  });

  it("logout clears the session and returns to /login", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { permissions: [] } });
    const router = renderLayout(userToken);
    await userEvent.click(await screen.findByRole("button", { name: "Account menu of alice" }));
    const button = await screen.findByRole("button", { name: /log out/i });
    await act(async () => {
      await userEvent.click(button);
    });
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });
});
