import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";

import "../../i18n/i18n";
import i18n from "../../i18n/i18n";

vi.mock("../../api/apiClient");

import apiClient from "../../api/apiClient";
import LoginPage from "../LoginPage";
import AppLayout from "../../components/AppLayout";
import { AuthProvider } from "../../context/AuthContext";
import { resetAuthConfigCache } from "../../api/authConfig";
import { resetHCaptchaLoader } from "../../components/HCaptcha";
import { httpError } from "../../test/axiosError";

// Spec Phase 2 on the login page (task 33): CAPTCHA, verification modal,
// deactivated accounts.

function makeJwt(payload: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${enc({ alg: "HS256", typ: "JWT" })}.${enc(payload)}.sig`;
}

const TOKEN = makeJwt({ user_id: 1, username: "alice", role: "User", exp: 9999999999 });

function config(overrides: Record<string, unknown> = {}) {
  return { data: { captcha_site_key: null, email_verification: false, ...overrides } };
}

function renderLogin(state?: unknown) {
  const router = createMemoryRouter(
    [
      {
        element: <AppLayout />,
        children: [
          { path: "/login", element: <LoginPage /> },
          { path: "/credentials", element: <p>credentials page</p> },
        ],
      },
    ],
    { initialEntries: [{ pathname: "/login", state }] }
  );
  render(
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
  return router;
}

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Username"), "alice");
  await user.type(screen.getByLabelText("Password"), "Str0ngPassw0rd!");
  await user.click(screen.getByRole("button", { name: "Log In" }));
}

describe("LoginPage — spec Phase 2", () => {
  beforeEach(async () => {
    resetAuthConfigCache();
    resetHCaptchaLoader();
    await i18n.changeLanguage("en");
    vi.mocked(apiClient.get).mockImplementation((url: string) =>
      url === "/api/auth/config" ? Promise.resolve(config()) : Promise.resolve({ data: { permissions: [] } })
    );
  });

  afterEach(() => {
    vi.clearAllMocks();
    delete window.hcaptcha;
    document.head.querySelectorAll("script[src*='hcaptcha']").forEach((s) => s.remove());
  });

  it("logs in without CAPTCHA when it is not configured", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { access_token: TOKEN, email_verification_required: false },
    });
    const router = renderLogin();
    await fillAndSubmit();

    await waitFor(() => expect(router.state.location.pathname).toBe("/credentials"));
    expect(apiClient.post).toHaveBeenCalledWith("/api/auth/login", {
      username: "alice",
      password: "Str0ngPassw0rd!",
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hcaptcha")).not.toBeInTheDocument();
  });

  it("shows the verification modal after logging in unverified (2.7)", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        access_token: TOKEN,
        email_verification_required: true,
        deactivation_deadline: "2026-12-14",
      },
    });
    renderLogin();
    await fillAndSubmit();

    const dialog = await screen.findByRole("dialog", { name: "Verify your email" });
    expect(dialog).toHaveTextContent("December 14, 2026");
    await userEvent.setup().click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("credentials page")).toBeInTheDocument();
  });

  it("explains a deactivated account (2.9)", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(httpError(403, "Account deactivated."));
    renderLogin();
    await fillAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent(/deactivated/i);
  });

  it("keeps the generic message for wrong credentials (2.3)", async () => {
    vi.mocked(apiClient.post).mockRejectedValue(httpError(401, "Invalid credentials."));
    renderLogin();
    await fillAndSubmit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password.");
  });

  it("confirms sign-up and mentions verification when it is on", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(config({ email_verification: true }));
    renderLogin({ registered: true });
    expect(await screen.findByRole("status")).toHaveTextContent(/verify your address/i);
  });

  describe("with CAPTCHA configured (2.6)", () => {
    let solve: (token: string) => void;
    const hc = {
      render: vi.fn(),
      reset: vi.fn(),
      remove: vi.fn(),
    };

    beforeEach(() => {
      hc.render.mockImplementation((_el: HTMLElement, params: { callback: (t: string) => void }) => {
        solve = params.callback;
        return "widget-1";
      });
      window.hcaptcha = hc;
      vi.mocked(apiClient.get).mockResolvedValue(config({ captcha_site_key: "site-key" }));
    });

    it("requires the challenge before submitting, then sends its token", async () => {
      vi.mocked(apiClient.post).mockResolvedValue({ data: { access_token: TOKEN } });
      renderLogin();
      await waitFor(() => expect(hc.render).toHaveBeenCalled());
      expect(hc.render.mock.calls[0][1]).toMatchObject({ sitekey: "site-key", hl: "en" });

      await fillAndSubmit();
      expect(await screen.findByRole("alert")).toHaveTextContent(/complete the CAPTCHA/i);
      expect(apiClient.post).not.toHaveBeenCalled();

      act(() => solve("captcha-token"));
      await userEvent.setup().click(screen.getByRole("button", { name: "Log In" }));
      await waitFor(() =>
        expect(apiClient.post).toHaveBeenCalledWith("/api/auth/login", {
          username: "alice",
          password: "Str0ngPassw0rd!",
          captcha_token: "captcha-token",
        })
      );
    });

    it("resets the challenge after a rejected login", async () => {
      vi.mocked(apiClient.post).mockRejectedValue(httpError(400, "CAPTCHA verification failed."));
      renderLogin();
      await waitFor(() => expect(hc.render).toHaveBeenCalled());
      act(() => solve("used-token"));
      await fillAndSubmit();

      expect(await screen.findByRole("alert")).toHaveTextContent(/CAPTCHA check failed/i);
      expect(hc.reset).toHaveBeenCalledWith("widget-1");

      // The used token is gone: a new submit asks for the challenge again.
      vi.mocked(apiClient.post).mockClear();
      await userEvent.setup().click(screen.getByRole("button", { name: "Log In" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(/complete the CAPTCHA/i);
      expect(apiClient.post).not.toHaveBeenCalled();
    });

    it("loads the hCaptcha script when it is not present yet", async () => {
      delete window.hcaptcha;
      renderLogin();
      const script = await waitFor(() => {
        const s = document.head.querySelector<HTMLScriptElement>("script[src*='hcaptcha']");
        expect(s).not.toBeNull();
        return s!;
      });
      expect(script.src).toBe("https://js.hcaptcha.com/1/api.js?render=explicit");

      window.hcaptcha = hc;
      act(() => script.onload?.(new Event("load")));
      await waitFor(() => expect(hc.render).toHaveBeenCalled());
    });

    it("tells the user when the script cannot load", async () => {
      delete window.hcaptcha;
      renderLogin();
      const script = await waitFor(() => {
        const s = document.head.querySelector<HTMLScriptElement>("script[src*='hcaptcha']");
        expect(s).not.toBeNull();
        return s!;
      });
      act(() => script.onerror?.(new Event("error")));
      expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);
    });
  });
});
