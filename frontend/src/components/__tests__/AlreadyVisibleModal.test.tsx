import { describe, it, expect, vi, beforeEach, type Mock } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Initialize i18n before importing the component so useTranslation() resolves
// real English strings instead of returning the raw key.
import "../../i18n/i18n";

import AlreadyVisibleModal from "../AlreadyVisibleModal";

// ── Helpers ──────────────────────────────────────────────────────────────────

function renderModal(onContinue: () => void, onCancel: () => void) {
  return render(
    <AlreadyVisibleModal onContinue={onContinue} onCancel={onCancel} />
  );
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("AlreadyVisibleModal", () => {
  let onContinue: Mock<() => void>;
  let onCancel: Mock<() => void>;

  beforeEach(() => {
    onContinue = vi.fn();
    onCancel = vi.fn();
  });

  // ── Rendering ─────────────────────────────────────────────────────────────

  it("renders the modal title (Requirement 5.10)", () => {
    renderModal(onContinue, onCancel);
    // The title key resolves to "Password Already Visible"
    expect(
      screen.getByRole("heading", { name: /password already visible/i })
    ).toBeInTheDocument();
  });

  it("renders the warning body text (Requirement 5.10)", () => {
    renderModal(onContinue, onCancel);
    expect(
      screen.getByText(/another password is currently visible/i)
    ).toBeInTheDocument();
  });

  it("renders both Continue and Cancel buttons", () => {
    renderModal(onContinue, onCancel);
    expect(
      screen.getByRole("button", { name: /continue/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /cancel/i })
    ).toBeInTheDocument();
  });

  // ── Continue button (Requirement 5.11) ────────────────────────────────────

  it("clicking Continue calls onContinue exactly once (Requirement 5.11)", () => {
    renderModal(onContinue, onCancel);
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("clicking Continue does NOT call onCancel (Requirement 5.11)", () => {
    renderModal(onContinue, onCancel);
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onCancel).not.toHaveBeenCalled();
  });

  // ── Cancel button (Requirement 5.12) ──────────────────────────────────────

  it("clicking Cancel calls onCancel exactly once (Requirement 5.12)", () => {
    renderModal(onContinue, onCancel);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("clicking Cancel does NOT call onContinue (Requirement 5.12)", () => {
    renderModal(onContinue, onCancel);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onContinue).not.toHaveBeenCalled();
  });

  // ── Independence — the two callbacks fire only once each (Requirements 5.11, 5.12) ──

  it("Continue and Cancel fire independently — clicking both in sequence calls each exactly once", () => {
    renderModal(onContinue, onCancel);

    // Click Continue first
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(0);

    // Click Cancel second
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onContinue).toHaveBeenCalledTimes(1); // still just 1
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("clicking Cancel then Continue each fires exactly its own callback (Requirements 5.11, 5.12)", () => {
    renderModal(onContinue, onCancel);

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onContinue).toHaveBeenCalledTimes(0);

    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(onCancel).toHaveBeenCalledTimes(1); // still just 1
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  // ── Keyboard: Escape triggers onCancel (Requirement 5.12) ─────────────────

  it("pressing Escape calls onCancel and not onContinue (Requirement 5.12)", () => {
    renderModal(onContinue, onCancel);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onContinue).not.toHaveBeenCalled();
  });

  // ── Backdrop click triggers onCancel ──────────────────────────────────────

  it("clicking the backdrop calls onCancel and not onContinue (Requirement 5.12)", () => {
    renderModal(onContinue, onCancel);
    // The backdrop is the outermost div with role="alertdialog"
    const backdrop = screen.getByRole("alertdialog");
    fireEvent.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onContinue).not.toHaveBeenCalled();
  });
});
