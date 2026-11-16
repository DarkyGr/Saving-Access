import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import "../../i18n/i18n";
import SystemSettingsPage from "../SystemSettingsPage";
import UnlockPage from "../UnlockPage";
import apiClient from "../../api/apiClient";
import { httpError } from "../../test/axiosError";

const PARAMS = [
  { key: "lockout_attempts", group: "security", value: 5, default: 5, minimum: 3, maximum: 20 },
  { key: "admin_reauth_minutes", group: "security", value: 5, default: 5, minimum: 0, maximum: 60 },
  { key: "session_idle_minutes", group: "sessions", value: 15, default: 15, minimum: 5, maximum: 240 },
];

describe("SystemSettingsPage (task 37.5)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: PARAMS });
  });

  it("shows each value with its range and suggested value, and saves only what changed", async () => {
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({
      data: PARAMS.map((p) => (p.key === "lockout_attempts" ? { ...p, value: 7 } : p)),
    });
    render(<SystemSettingsPage />);
    const field = await screen.findByLabelText("Failed attempts before locking");
    expect(screen.getAllByText("From 3 to 20 · suggested 5").length).toBe(1);
    await userEvent.clear(field);
    await userEvent.type(field, "7");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(put).toHaveBeenCalledWith("/api/admin/settings", { lockout_attempts: 7 });
    expect(await screen.findByRole("status")).toHaveTextContent("Parameters saved.");
  });

  it("refuses a value out of range before asking the server", async () => {
    const put = vi.spyOn(apiClient, "put");
    render(<SystemSettingsPage />);
    const field = await screen.findByLabelText("Failed attempts before locking");
    await userEvent.clear(field);
    await userEvent.type(field, "2");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(put).not.toHaveBeenCalled();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Use a whole number from 3 to 20.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use the suggested value" }));
    expect(field).toHaveValue(5);
  });
});

describe("UnlockPage (task 37.5)", () => {
  beforeEach(() => vi.restoreAllMocks());

  function open(url: string) {
    render(
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/unlock" element={<UnlockPage />} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("uses the link only when the button is pressed", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    open("/unlock?token=abc");
    expect(post).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Unlock my account" }));
    expect(post).toHaveBeenCalledWith("/api/auth/unlock", { token: "abc" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Your account is unlocked.");
  });

  it("explains a used or expired link", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(400, "Invalid or expired link."));
    open("/unlock?token=old");
    await userEvent.click(screen.getByRole("button", { name: "Unlock my account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is not valid");
  });
});
