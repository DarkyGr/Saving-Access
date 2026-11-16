import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
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

const BASE = {
  display_name: null,
  email_verified: true,
  status: "active",
  deactivated_by: null,
  deactivated_at: null,
  deactivation_reason: null,
  created: "2026-11-01T10:00:00Z",
};
const USERS = [
  { ...BASE, user_id: 1, user_code: "SP-ROOT22", username: "root", email: "root@example.com", role: "Admin" },
  { ...BASE, user_id: 2, user_code: "SP-ALIC33", username: "alice", email: "alice@example.com", role: "User" },
  {
    ...BASE,
    user_id: 3,
    user_code: "SP-BOBB44",
    username: "bob",
    email: "bob@example.com",
    role: "User",
    status: "deactivated",
    deactivated_by: "admin",
    deactivated_at: "2026-11-10T09:00:00Z",
    deactivation_reason: "Left the team",
  },
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

  it("finds an account by user ID and filters by status", async () => {
    renderPage();
    await screen.findByLabelText("Change the role of alice");
    await userEvent.type(screen.getByPlaceholderText("Search by name, email or user ID"), "sp-alic");
    expect(screen.getByText("alice")).toBeInTheDocument();
    expect(screen.queryByText("bob")).not.toBeInTheDocument();
    await userEvent.clear(screen.getByPlaceholderText("Search by name, email or user ID"));
    await userEvent.selectOptions(screen.getByLabelText("Status"), "deactivated");
    expect(screen.getByText("bob")).toBeInTheDocument();
    expect(screen.getByText("Reason: Left the team")).toBeInTheDocument();
    expect(screen.queryByText("alice")).not.toBeInTheDocument();
  });

  it("deactivates another account with a reason, never its own", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: { ...USERS[1], status: "deactivated", deactivated_by: "admin", deactivation_reason: "Done here" } });
    renderPage();
    await screen.findByLabelText("Change the role of alice");
    expect(screen.queryByLabelText("Deactivate root")).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText("Deactivate alice"));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("at least 3 characters");
    expect(post).not.toHaveBeenCalled();

    await userEvent.type(within(dialog).getByLabelText("Reason (sent to the person)"), "  Done   here ");
    await userEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));
    expect(post).toHaveBeenCalledWith("/api/admin/users/2/deactivate", { reason: "Done here" });
    expect(await screen.findByText("alice was deactivated.")).toBeInTheDocument();
    expect(screen.getByLabelText("Reactivate alice")).toBeInTheDocument();
  });

  it("reactivates a deactivated account after confirming", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      data: { ...USERS[2], status: "active", deactivated_by: null, deactivation_reason: null },
    });
    renderPage();
    await userEvent.click(await screen.findByLabelText("Reactivate bob"));
    await userEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Reactivate" }));
    expect(post).toHaveBeenCalledWith("/api/admin/users/3/reactivate", undefined);
    expect(await screen.findByText("bob was reactivated.")).toBeInTheDocument();
    expect(screen.getByLabelText("Deactivate bob")).toBeInTheDocument();
  });
});
