import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import PasswordInput from "../PasswordInput";

// Mock react-i18next so the component renders without a full i18n provider.
// The mock returns the translation key's leaf segment as the translated string,
// matching the real en.json values used in aria-labels.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        "credentials.revealButton": "Show password",
        "credentials.hideButton": "Hide password",
      };
      return translations[key] ?? key;
    },
    i18n: { changeLanguage: vi.fn() },
  }),
}));

describe("PasswordInput — Eye_Toggle", () => {
  const user = userEvent.setup();

  beforeEach(() => {
    // Render a fresh instance before each test
  });

  it("1. renders with type='password' by default (password is masked)", () => {
    render(<PasswordInput />);

    // Use querySelector because input[type=password] is not a "textbox" role
    const passwordInput = document.querySelector("input") as HTMLInputElement;
    expect(passwordInput).not.toBeNull();
    expect(passwordInput.type).toBe("password");
  });

  it("2. clicking Eye_Toggle reveals the password (type changes to 'text')", async () => {
    render(<PasswordInput />);

    const toggleBtn = screen.getByRole("button", { name: "Show password" });
    await user.click(toggleBtn);

    const input = document.querySelector("input") as HTMLInputElement;
    expect(input.type).toBe("text");
  });

  it("3. clicking Eye_Toggle a second time masks the password again (type back to 'password')", async () => {
    render(<PasswordInput />);

    const toggleBtn = screen.getByRole("button", { name: "Show password" });
    // First click — reveal
    await user.click(toggleBtn);
    expect((document.querySelector("input") as HTMLInputElement).type).toBe("text");

    // Second click — mask again
    const hideBtn = screen.getByRole("button", { name: "Hide password" });
    await user.click(hideBtn);
    expect((document.querySelector("input") as HTMLInputElement).type).toBe("password");
  });

  it("4. Eye_Toggle button has an accessible aria-label (uses t() for i18n)", () => {
    render(<PasswordInput />);

    // Before reveal: aria-label should be the reveal label
    const toggleBtn = screen.getByRole("button", { name: "Show password" });
    expect(toggleBtn).toHaveAttribute("aria-label", "Show password");
  });

  it("4b. aria-label switches to hide label when password is visible", async () => {
    render(<PasswordInput />);

    const revealBtn = screen.getByRole("button", { name: "Show password" });
    await user.click(revealBtn);

    // After reveal: aria-label should switch to the hide label
    const hideBtn = screen.getByRole("button", { name: "Hide password" });
    expect(hideBtn).toHaveAttribute("aria-label", "Hide password");
  });

  it("toggle button has aria-pressed reflecting visibility state", async () => {
    render(<PasswordInput />);

    const btn = screen.getByRole("button", { name: "Show password" });
    expect(btn).toHaveAttribute("aria-pressed", "false");

    await user.click(btn);
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });
});
