import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import "../../i18n/i18n";
import i18n from "../../i18n/i18n";

vi.mock("../../api/apiClient");

import apiClient from "../../api/apiClient";
import VerifyEmailModal from "../VerifyEmailModal";
import { httpError } from "../../test/axiosError";

describe("VerifyEmailModal (2.7, 2.8)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });
  afterEach(() => vi.clearAllMocks());

  it("shows the deadline and resends in the UI language", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: {} });
    render(<VerifyEmailModal deadline="2026-12-14" onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toHaveTextContent("December 14, 2026");

    await userEvent.setup().click(screen.getByRole("button", { name: "Resend email" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/new verification email/i);
    expect(apiClient.post).toHaveBeenCalledWith("/api/profile/verification-email", {
      language: "en",
    });
    expect(screen.getByRole("button", { name: "Resend email" })).toBeDisabled();
  });

  it("works without a deadline", () => {
    render(<VerifyEmailModal deadline={null} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toHaveTextContent(/not verified yet/i);
  });

  it.each([
    [409, /already verified/i],
    [429, /try again later/i],
    [500, /could not be sent/i],
  ])("maps HTTP %i on resend", async (status, text) => {
    vi.mocked(apiClient.post).mockRejectedValue(httpError(status));
    render(<VerifyEmailModal deadline={null} onClose={vi.fn()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Resend email" }));
    expect(await screen.findByRole("status")).toHaveTextContent(text);
  });

  it("closes with the button and with Escape", async () => {
    const onClose = vi.fn();
    render(<VerifyEmailModal deadline={null} onClose={onClose} />);
    const user = userEvent.setup();
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("speaks Spanish", async () => {
    await i18n.changeLanguage("es");
    render(<VerifyEmailModal deadline="2026-12-14" onClose={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: "Verifica tu correo" })).toHaveTextContent(
      "14 de diciembre de 2026"
    );
  });
});
