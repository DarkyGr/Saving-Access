import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Initialize i18n before importing the component so useTranslation() resolves
// real English strings instead of returning the raw key.
import "../../i18n/i18n";

import PasswordConfirmModal from "../PasswordConfirmModal";

// ── Helpers ──────────────────────────────────────────────────────────────────

function renderModal(
  onConfirm: (password: string) => void,
  onCancel: () => void,
  extras?: { error?: string; isLoading?: boolean }
) {
  return render(
    <PasswordConfirmModal
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...extras}
    />
  );
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("PasswordConfirmModal", () => {
  const user = userEvent.setup();

  let onConfirm: Mock<(password: string) => void>;
  let onCancel: Mock<() => void>;

  beforeEach(() => {
    onConfirm = vi.fn();
    onCancel = vi.fn();
  });

  // ── Rendering ─────────────────────────────────────────────────────────────

  it("renders the modal title (Requirement 4.8)", () => {
    renderModal(onConfirm, onCancel);
    expect(
      screen.getByRole("heading", { name: /confirm your account password/i })
    ).toBeInTheDocument();
  });

  it("renders the description text", () => {
    renderModal(onConfirm, onCancel);
    expect(
      screen.getByText(/enter your account password to continue/i)
    ).toBeInTheDocument();
  });

  it("renders both Confirm and Cancel buttons", () => {
    renderModal(onConfirm, onCancel);
    expect(
      screen.getByRole("button", { name: /confirm/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /cancel/i })
    ).toBeInTheDocument();
  });

  // ── 1. onConfirm called with typed value (Requirement 4.8) ───────────────

  it("clicking Confirm calls onConfirm with the typed password (Requirement 4.8)", async () => {
    renderModal(onConfirm, onCancel);

    const passwordInput = document.querySelector("input") as HTMLInputElement;
    await user.type(passwordInput, "MySecret123!");

    const confirmBtn = screen.getByRole("button", { name: /confirm/i });
    await user.click(confirmBtn);

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("MySecret123!");
  });

  it("onConfirm is NOT called when input is empty and form is submitted", async () => {
    renderModal(onConfirm, onCancel);
    // Submit via keyboard Enter — confirm button is disabled when empty
    const passwordInput = document.querySelector("input") as HTMLInputElement;
    fireEvent.keyDown(passwordInput, { key: "Enter", code: "Enter" });
    expect(onConfirm).not.toHaveBeenCalled();
  });

  // ── 2. Cancel calls onCancel and not onConfirm (Requirement 5.5) ─────────

  it("clicking Cancel calls onCancel exactly once (Requirement 5.5)", async () => {
    renderModal(onConfirm, onCancel);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("clicking Cancel does NOT call onConfirm (Requirement 5.5)", async () => {
    renderModal(onConfirm, onCancel);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  // ── 3. Confirm button disabled when input is empty (Requirement 6.5) ─────

  it("Confirm button is disabled when password field is empty (Requirement 6.5)", () => {
    renderModal(onConfirm, onCancel);
    const confirmBtn = screen.getByRole("button", { name: /confirm/i });
    expect(confirmBtn).toBeDisabled();
  });

  it("Confirm button becomes enabled after typing a non-empty password (Requirement 6.5)", async () => {
    renderModal(onConfirm, onCancel);
    const passwordInput = document.querySelector("input") as HTMLInputElement;
    await user.type(passwordInput, "a");
    expect(screen.getByRole("button", { name: /confirm/i })).not.toBeDisabled();
  });

  it("Confirm button remains disabled when password is only whitespace (Requirement 6.5)", async () => {
    renderModal(onConfirm, onCancel);
    const passwordInput = document.querySelector("input") as HTMLInputElement;
    await user.type(passwordInput, "   ");
    expect(screen.getByRole("button", { name: /confirm/i })).toBeDisabled();
  });

  // ── 4. Eye_Toggle works inside the modal ─────────────────────────────────

  it("password field starts masked (type='password')", () => {
    renderModal(onConfirm, onCancel);
    const passwordInput = document.querySelector("input") as HTMLInputElement;
    expect(passwordInput.type).toBe("password");
  });

  it("clicking Eye_Toggle reveals the password (type changes to 'text')", async () => {
    renderModal(onConfirm, onCancel);
    await user.click(screen.getByRole("button", { name: /show password/i }));
    const passwordInput = document.querySelector("input") as HTMLInputElement;
    expect(passwordInput.type).toBe("text");
  });

  it("clicking Eye_Toggle a second time masks the password again (type back to 'password')", async () => {
    renderModal(onConfirm, onCancel);

    // First click — reveal
    await user.click(screen.getByRole("button", { name: /show password/i }));
    expect((document.querySelector("input") as HTMLInputElement).type).toBe("text");

    // Second click — mask again
    await user.click(screen.getByRole("button", { name: /hide password/i }));
    expect((document.querySelector("input") as HTMLInputElement).type).toBe("password");
  });

  // ── 5. Escape key calls onCancel (Requirement 7.4) ───────────────────────

  it("pressing Escape calls onCancel and not onConfirm (Requirement 7.4)", () => {
    renderModal(onConfirm, onCancel);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  // ── 6. Backdrop click calls onCancel (Requirement 7.4) ───────────────────

  it("clicking the backdrop calls onCancel and not onConfirm (Requirement 7.4)", () => {
    renderModal(onConfirm, onCancel);
    // The backdrop is the outermost div with role="dialog"
    const backdrop = screen.getByRole("dialog");
    fireEvent.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  // ── 7. Error prop is displayed ────────────────────────────────────────────

  it("renders the error message when error prop is provided", () => {
    renderModal(onConfirm, onCancel, {
      error: "Incorrect account password.",
    });
    expect(
      screen.getByText(/incorrect account password/i)
    ).toBeInTheDocument();
  });

  it("does not render an error when error prop is not provided", () => {
    renderModal(onConfirm, onCancel);
    expect(
      screen.queryByText(/incorrect account password/i)
    ).not.toBeInTheDocument();
  });

  // ── 8. isLoading disables buttons and shows loading text ─────────────────

  it("isLoading disables the Confirm button", () => {
    renderModal(onConfirm, onCancel, { isLoading: true });
    // The confirm button shows "Loading…" when isLoading is true
    expect(screen.getByRole("button", { name: /loading/i })).toBeDisabled();
  });

  it("isLoading disables the Cancel button", () => {
    renderModal(onConfirm, onCancel, { isLoading: true });
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  });

  it("isLoading shows loading text on the Confirm button", () => {
    renderModal(onConfirm, onCancel, { isLoading: true });
    expect(screen.getByRole("button", { name: /loading/i })).toBeInTheDocument();
  });

  it("isLoading hides the normal Confirm button text", () => {
    renderModal(onConfirm, onCancel, { isLoading: true });
    // "Confirm" button text is replaced by "Loading…" during loading
    expect(screen.queryByRole("button", { name: /^confirm$/i })).not.toBeInTheDocument();
  });
});
