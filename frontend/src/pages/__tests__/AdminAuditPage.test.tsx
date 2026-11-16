import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../../i18n/i18n";
import AdminAuditPage from "../AdminAuditPage";
import apiClient from "../../api/apiClient";

const boss = { user_id: 1, user_code: "SP-BOSS22", username: "boss" };
const alice = { user_id: 2, user_code: "SP-ALIC33", username: "alice" };

const ITEMS = [
  { log_id: 3, at: "2026-11-16T10:00:00Z", action: "user.role", actor: boss, target: alice, record_id: null, detail: "User→Admin" },
  { log_id: 2, at: "2026-11-16T09:00:00Z", action: "credential.reveal", actor: alice, target: null, record_id: 7, detail: null },
  { log_id: 1, at: "2026-11-15T09:00:00Z", action: "account.login", actor: alice, target: null, record_id: null, detail: null },
];

describe("AdminAuditPage (task 37.4)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("lists who did what, naming credentials by number only", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { items: ITEMS, truncated: false } });
    render(<AdminAuditPage />);
    expect(await screen.findByRole("cell", { name: "Changed a role" })).toBeInTheDocument();
    expect(screen.getByText("User → Admin")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Revealed a password" })).toBeInTheDocument();
    expect(screen.getByText("Credential #7")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Signed in" })).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledWith("/api/admin/audit", { params: {} });
  });

  it("asks the server again when a filter changes", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: { items: ITEMS, truncated: false } });
    render(<AdminAuditPage />);
    await screen.findByRole("cell", { name: "Changed a role" });

    await userEvent.selectOptions(screen.getByLabelText("Action"), "user.role");
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith("/api/admin/audit", { params: { action: "user.role" } })
    );
    await userEvent.type(screen.getByPlaceholderText("Person: name, email or user ID"), "alice");
    await waitFor(() =>
      expect(get).toHaveBeenLastCalledWith("/api/admin/audit", { params: { action: "user.role", q: "alice" } })
    );
  });

  it("says when only the latest entries are shown, or when nothing matches", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: { items: ITEMS, truncated: true } });
    const { unmount } = render(<AdminAuditPage />);
    expect(await screen.findByText(/Showing the latest 3 entries/)).toBeInTheDocument();
    unmount();

    vi.spyOn(apiClient, "get").mockResolvedValueOnce({ data: { items: [], truncated: false } });
    render(<AdminAuditPage />);
    expect(await screen.findByText("Nothing matches these filters.")).toBeInTheDocument();
  });
});
