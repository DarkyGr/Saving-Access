import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import "../../i18n/i18n";
import AdminUsersPage from "../AdminUsersPage";
import { AuthProvider, useAuth } from "../../context/AuthContext";
import apiClient from "../../api/apiClient";
import { httpError } from "../../test/axiosError";

function makeJwt(payload: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${enc({ alg: "HS256", typ: "JWT" })}.${enc(payload)}.sig`;
}

const adminToken = makeJwt({ user_id: 1, username: "root", role: "Admin", exp: 9999999999 });

function AsAdmin() {
  const { login, user } = useAuth();
  useEffect(() => {
    login(adminToken);
  }, [login]);
  return user ? <AdminUsersPage /> : null;
}

const USERS = [
  { user_id: 1, username: "root", email: "root@example.com", role: "Admin", email_verified: true },
  { user_id: 2, username: "alice", email: "alice@example.com", role: "User", email_verified: true },
];

function renderPage() {
  render(
    <AuthProvider>
      <AsAdmin />
    </AuthProvider>
  );
}

describe("AdminUsersPage (task 37.1)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: USERS });
  });

  it("lists users with their role and locks the Admin's own row", async () => {
    renderPage();
    const own = await screen.findByLabelText("Change the role of root");
    const other = screen.getByLabelText("Change the role of alice");
    expect(apiClient.get).toHaveBeenCalledWith("/api/admin/users");
    expect(own).toBeDisabled();
    expect(own).toHaveValue("Admin");
    expect(screen.getAllByText("You cannot change your own role.").length).toBeGreaterThan(0);
    expect(other).toBeEnabled();
    expect(other).toHaveValue("User");
    expect(screen.queryByText(/profile/i)).not.toBeInTheDocument();
  });

  it("changes another user's role", async () => {
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: { user_id: 2, role: "Admin" } });
    renderPage();
    const select = await screen.findByLabelText("Change the role of alice");
    await userEvent.selectOptions(select, "Admin");
    expect(put).toHaveBeenCalledWith("/api/admin/users/2/role", { role: "Admin" });
    expect(await screen.findByRole("status")).toHaveTextContent("Role updated.");
    expect(select).toHaveValue("Admin");
  });

  it("shows an error and keeps the old role when the change fails", async () => {
    vi.spyOn(apiClient, "put").mockRejectedValue(httpError(500, "boom"));
    renderPage();
    const select = await screen.findByLabelText("Change the role of alice");
    await userEvent.selectOptions(select, "Admin");
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Could not change the role.")
    );
    expect(select).toHaveValue("User");
  });
});
