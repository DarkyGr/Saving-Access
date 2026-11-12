import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeAll } from "vitest";
import i18next from "i18next";
import { initReactI18next, I18nextProvider, useTranslation } from "react-i18next";

import LanguageToggle from "../LanguageToggle";
import en from "../../i18n/en.json";
import es from "../../i18n/es.json";

// ---------------------------------------------------------------------------
// Isolated i18next instance — does not pollute the app-level singleton
// ---------------------------------------------------------------------------
const testI18n = i18next.createInstance();

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: "en",
    resources: {
      en: { translation: en },
      es: { translation: es },
    },
    interpolation: { escapeValue: false },
  });
});

// ---------------------------------------------------------------------------
// Helper: a small consumer that renders a translated string so we can assert
// that t() output has actually changed after a language switch.
// ---------------------------------------------------------------------------
function TranslationProbe({ tKey }: { tKey: string }) {
  const { t } = useTranslation();
  return <span data-testid="probe">{t(tKey)}</span>;
}

// ---------------------------------------------------------------------------
// Wrapper that resets the i18n instance to English before each render so
// tests are independent of one another.
// ---------------------------------------------------------------------------
function renderWithI18n(tKey = "nav.credentials") {
  return render(
    <I18nextProvider i18n={testI18n}>
      <LanguageToggle />
      <TranslationProbe tKey={tKey} />
    </I18nextProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("LanguageToggle", () => {
  const user = userEvent.setup();

  // Reset to English before every test so they are independent
  beforeAll(async () => {
    await testI18n.changeLanguage("en");
  });

  it("1. renders EN and ES buttons", async () => {
    await act(async () => {
      await testI18n.changeLanguage("en");
    });
    renderWithI18n();

    expect(screen.getByRole("button", { name: /english/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /spanish/i })).toBeInTheDocument();
  });

  it("2. EN button has aria-pressed='true' by default", async () => {
    await act(async () => {
      await testI18n.changeLanguage("en");
    });
    renderWithI18n();

    const enBtn = screen.getByRole("button", { name: /english/i });
    const esBtn = screen.getByRole("button", { name: /spanish/i });

    expect(enBtn).toHaveAttribute("aria-pressed", "true");
    expect(esBtn).toHaveAttribute("aria-pressed", "false");
  });

  it("3. clicking ES changes translated strings to Spanish", async () => {
    await act(async () => {
      await testI18n.changeLanguage("en");
    });
    renderWithI18n("nav.credentials");

    // Probe starts in English
    expect(screen.getByTestId("probe")).toHaveTextContent("My Credentials");

    const esBtn = screen.getByRole("button", { name: /spanish/i });

    await act(async () => {
      await user.click(esBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("Mis Credenciales");
    });
  });

  it("4. clicking EN after ES reverts translated strings to English", async () => {
    await act(async () => {
      await testI18n.changeLanguage("es");
    });
    renderWithI18n("nav.credentials");

    // Probe starts in Spanish
    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("Mis Credenciales");
    });

    const enBtn = screen.getByRole("button", { name: /inglés/i });

    await act(async () => {
      await user.click(enBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("probe")).toHaveTextContent("My Credentials");
    });
  });

  it("5. window.location.reload is never called during language change", async () => {
    await act(async () => {
      await testI18n.changeLanguage("en");
    });

    // jsdom's window.location.reload is non-configurable, so we replace the
    // whole location object with a plain stub that we can spy on.
    const reloadMock = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, reload: reloadMock },
      writable: true,
      configurable: true,
    });

    renderWithI18n();

    const esBtn = screen.getByRole("button", { name: /spanish/i });
    await act(async () => {
      await user.click(esBtn);
    });

    const enBtn = screen.getByRole("button", { name: /inglés/i });
    await act(async () => {
      await user.click(enBtn);
    });

    expect(reloadMock).not.toHaveBeenCalled();
  });

  it("6. sessionStorage is updated with the chosen language code", async () => {
    await act(async () => {
      await testI18n.changeLanguage("en");
    });
    renderWithI18n();

    const esBtn = screen.getByRole("button", { name: /spanish/i });
    await act(async () => {
      await user.click(esBtn);
    });

    expect(sessionStorage.getItem("i18nextLng")).toBe("es");

    const enBtn = screen.getByRole("button", { name: /inglés/i });
    await act(async () => {
      await user.click(enBtn);
    });

    expect(sessionStorage.getItem("i18nextLng")).toBe("en");
  });
});
