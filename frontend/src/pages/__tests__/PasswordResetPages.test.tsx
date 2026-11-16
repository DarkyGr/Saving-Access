import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import "../../i18n/i18n";
import ForgotPasswordPage from "../ForgotPasswordPage";
import ResetPasswordPage from "../ResetPasswordPage";
import apiClient from "../../api/apiClient";
import { httpError } from "../../test/axiosError";

function open(url: string) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Forgot password (task 37.5)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("always shows the same answer after sending", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    open("/forgot-password");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(post).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Username or email"), " alice ");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(post).toHaveBeenCalledWith("/api/auth/forgot-password", { account: "alice", language: expect.any(String) });
    expect(await screen.findByRole("status")).toHaveTextContent("If that account exists");
  });

  it("checks the rules before setting the new password", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ data: {} });
    open("/reset-password?token=abc");
    await userEvent.type(screen.getByLabelText("New password *", { exact: true }), "short");
    await userEvent.click(screen.getByRole("button", { name: "Save the new password" }));
    expect(post).not.toHaveBeenCalled();

    await userEvent.clear(screen.getByLabelText("New password *", { exact: true }));
    await userEvent.type(screen.getByLabelText("New password *", { exact: true }), "N3wStr0ngPass!");
    await userEvent.type(screen.getByLabelText("Confirm the new password *", { exact: true }), "N3wStr0ngPass!");
    await userEvent.click(screen.getByRole("button", { name: "Save the new password" }));
    expect(post).toHaveBeenCalledWith("/api/auth/reset-password", {
      token: "abc",
      password: "N3wStr0ngPass!",
      password_confirmation: "N3wStr0ngPass!",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Your password was changed");
  });

  it("explains a used or expired link and offers a new one", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(httpError(400, "Invalid or expired link."));
    open("/reset-password?token=old");
    await userEvent.type(screen.getByLabelText("New password *", { exact: true }), "N3wStr0ngPass!");
    await userEvent.type(screen.getByLabelText("Confirm the new password *", { exact: true }), "N3wStr0ngPass!");
    await userEvent.click(screen.getByRole("button", { name: "Save the new password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This link is not valid");
    expect(screen.getByRole("link", { name: "Ask for a new one" })).toHaveAttribute("href", "/forgot-password");
  });
});
