import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router";

import "../../i18n/i18n";

vi.mock("../../api/apiClient");

import apiClient from "../../api/apiClient";
import VerifyEmailPage from "../VerifyEmailPage";
import { httpError } from "../../test/axiosError";

function renderAt(url: string) {
  render(
    <StrictMode>
      <MemoryRouter initialEntries={[url]}>
        <VerifyEmailPage />
      </MemoryRouter>
    </StrictMode>
  );
}

describe("VerifyEmailPage (1.10)", () => {
  afterEach(() => vi.clearAllMocks());

  it("posts the token once and confirms", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { detail: "Email verified." } });
    renderAt("/verify-email?token=abc-123");
    expect(await screen.findByRole("alert")).toHaveTextContent(/has been verified/i);
    expect(apiClient.post).toHaveBeenCalledTimes(1); // StrictMode double effect guarded
    expect(apiClient.post).toHaveBeenCalledWith("/api/auth/verify-email", { token: "abc-123" });
    expect(screen.getByRole("link", { name: "Go to log in" })).toHaveAttribute("href", "/login");
  });

  it.each([
    [400, /invalid, has expired or was already used/i],
    [404, /invalid, has expired or was already used/i],
    [403, /deactivated/i],
    [500, /unexpected error/i],
  ])("maps HTTP %i to a message", async (status, text) => {
    vi.mocked(apiClient.post).mockRejectedValue(httpError(status));
    renderAt("/verify-email?token=t");
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("does not call the API without a token", async () => {
    renderAt("/verify-email");
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid/i);
    expect(apiClient.post).not.toHaveBeenCalled();
  });
});
