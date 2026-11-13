import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
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

  it("shows only the screens a User's profile permits", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { permissions: ["credentials"] } });
    renderLayout(userToken);
    expect(await screen.findByRole("link", { name: "My Credentials" })).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledWith("/api/profile/permissions");
    expect(screen.queryByRole("link", { name: "Save Credential" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Manage Users" })).not.toBeInTheDocument();
    expect(screen.getByTestId("current-user")).toHaveTextContent("alice");
  });

  it("shows admin links to an Admin without calling the permissions API", async () => {
    const get = vi.spyOn(apiClient, "get");
    renderLayout(adminToken);
    expect(await screen.findByRole("link", { name: "Manage Users" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Profiles" })).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it("logout clears the session and returns to /login", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { permissions: [] } });
    const router = renderLayout(userToken);
    const button = await screen.findByRole("button", { name: /log out/i });
    await act(async () => {
      await userEvent.click(button);
    });
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });
});
