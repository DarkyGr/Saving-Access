import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../../i18n/i18n";
import PasswordGenerator from "../form/PasswordGenerator";
import {
  DEFAULT_OPTIONS,
  generatePassword,
  randomBelow,
  strengthBits,
  strengthLevel,
} from "../../lib/passwordGenerator";

describe("generatePassword (Requirement 18)", () => {
  it("has the length and at least one of every kind that is on", () => {
    for (let i = 0; i < 200; i++) {
      const pw = generatePassword({ ...DEFAULT_OPTIONS, length: 8 });
      expect(pw).toHaveLength(8);
      expect(pw).toMatch(/[a-z]/);
      expect(pw).toMatch(/[A-Z]/);
      expect(pw).toMatch(/[0-9]/);
      expect(pw).toMatch(/[^A-Za-z0-9]/);
    }
  });

  it("leaves out kinds that are off and look-alike characters", () => {
    for (let i = 0; i < 200; i++) {
      const pw = generatePassword({ length: 64, lower: false, upper: true, digits: true, symbols: false, avoidSimilar: true });
      expect(pw).toMatch(/^[A-Z0-9]+$/);
      expect(pw).not.toMatch(/[IO01]/);
    }
  });

  it("refuses when no kind is on and clamps the length", () => {
    expect(() => generatePassword({ ...DEFAULT_OPTIONS, lower: false, upper: false, digits: false, symbols: false })).toThrow();
    expect(generatePassword({ ...DEFAULT_OPTIONS, length: 500 })).toHaveLength(64);
    expect(generatePassword({ ...DEFAULT_OPTIONS, length: 2 })).toHaveLength(8);
  });

  it("uses crypto.getRandomValues and stays unbiased", () => {
    const spy = vi.spyOn(crypto, "getRandomValues");
    const counts = new Array(10).fill(0);
    for (let i = 0; i < 20000; i++) counts[randomBelow(10)]++;
    expect(spy).toHaveBeenCalled();
    for (const n of counts) expect(Math.abs(n - 2000)).toBeLessThan(250);
    spy.mockRestore();
  });

  it("estimates the strength", () => {
    expect(strengthBits({ ...DEFAULT_OPTIONS, length: 20, avoidSimilar: false })).toBe(Math.floor(20 * Math.log2(87)));
    expect(strengthLevel(40)).toBe("weak");
    expect(strengthLevel(70)).toBe("good");
    expect(strengthLevel(120)).toBe("strong");
  });
});

describe("PasswordGenerator", () => {
  beforeEach(() => window.localStorage.clear());

  it("fills the field only when asked and remembers the options, not the password", async () => {
    const onUse = vi.fn();
    render(<PasswordGenerator onUse={onUse} />);
    await userEvent.click(screen.getByRole("button", { name: "Generate a strong password" }));
    const first = screen.getByTestId("generated-password").textContent!;
    expect(first).toHaveLength(20);
    expect(onUse).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Generate again" }));
    const second = screen.getByTestId("generated-password").textContent!;
    expect(second).not.toBe(first);

    await userEvent.click(screen.getByLabelText("Symbols (!@#…)"));
    expect(screen.getByTestId("generated-password").textContent).toMatch(/^[A-Za-z0-9]{20}$/);
    const stored = window.localStorage.getItem("savepass-generator-options")!;
    expect(JSON.parse(stored).symbols).toBe(false);
    expect(stored).not.toContain(screen.getByTestId("generated-password").textContent!);

    const shown = screen.getByTestId("generated-password").textContent!;
    await userEvent.click(screen.getByRole("button", { name: "Use this password" }));
    expect(onUse).toHaveBeenCalledWith(shown);
    expect(screen.queryByRole("group", { name: "Password generator" })).not.toBeInTheDocument();
  });

  it("asks for at least one kind of character", async () => {
    render(<PasswordGenerator onUse={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Generate a strong password" }));
    for (const label of ["Lowercase (a-z)", "Uppercase (A-Z)", "Digits (0-9)", "Symbols (!@#…)"]) {
      await userEvent.click(screen.getByLabelText(label));
    }
    expect(screen.getByText("Choose at least one kind of character.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use this password" })).toBeDisabled();
  });
});
