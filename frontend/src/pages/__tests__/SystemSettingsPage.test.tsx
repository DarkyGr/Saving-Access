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

const EMAIL = {
  email_verification: false,
  smtp: { host: "", port: 587, security: "starttls", username: "", from_address: "", has_password: false, configured: false },
  app_base_url_set: true,
  environment_backend: "console",
};

describe("SystemSettingsPage (task 37.5)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "get").mockImplementation((url: string) =>
      Promise.resolve({ data: url === "/api/admin/settings/email" ? EMAIL : PARAMS })
    );
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

describe("Email settings (task 37.5)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "get").mockImplementation((url: string) =>
      Promise.resolve({ data: url === "/api/admin/settings/email" ? { ...EMAIL, smtp: { ...EMAIL.smtp, has_password: true } } : PARAMS })
    );
  });

  it("saves the SMTP server with a write-only password", async () => {
    const put = vi.spyOn(apiClient, "put").mockResolvedValue({ data: EMAIL });
    render(<SystemSettingsPage />);
    expect(await screen.findByPlaceholderText("Saved — leave empty to keep it")).toHaveValue("");
    await userEvent.type(screen.getByLabelText("Server"), "smtp.example.com");
    await userEvent.click(screen.getByRole("button", { name: "Save email settings" }));
    expect(screen.getByRole("alert")).toHaveTextContent("the sender address");
    await userEvent.type(screen.getByLabelText("Sender address"), "vault@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Save email settings" }));
    expect(put).toHaveBeenCalledWith("/api/admin/settings/email", {
      email_verification: false,
      smtp: {
        host: "smtp.example.com",
        port: 587,
        security: "starttls",
        username: "",
        from_address: "vault@example.com",
        password: "",
        clear_password: false,
      },
    });
  });

  it("shows the result of a test email", async () => {
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: { ok: false, backend: "smtp", error: "SMTPAuthenticationError: bad" } });
    render(<SystemSettingsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Send a test email" }));
    expect(await screen.findByText("Could not send it: SMTPAuthenticationError: bad")).toBeInTheDocument();
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
