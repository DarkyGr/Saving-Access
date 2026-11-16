import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import "../../i18n/i18n";
import i18n from "../../i18n/i18n";
import HelpPage from "../HelpPage";
import { AuthProvider } from "../../context/AuthContext";
import apiClient from "../../api/apiClient";
import { matchRanges, splitMatches } from "../../lib/highlight";
import { USER_GUIDE } from "../../help/userGuide";
import { TECHNICAL_GUIDE } from "../../help/technicalGuide";

function open(guide: "user" | "technical", url = "/help") {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={[url]}>
        <HelpPage guide={guide} />
      </MemoryRouter>
    </AuthProvider>
  );
}

describe("Highlighting (Requirement 17.1)", () => {
  it("finds words ignoring case and accents and maps back to the text", () => {
    expect(matchRanges("Configuración rápida", "CONFIGURACION")).toEqual([[0, 13]]);
    expect(splitMatches("Two-step código", "codigo two")).toEqual([
      { text: "Two", match: true },
      { text: "-step ", match: false },
      { text: "código", match: true },
    ]);
    expect(matchRanges("anything", "  ")).toEqual([]);
  });
});

describe("Guides", () => {
  it("have the same sections in English and Spanish, with unique ids", () => {
    for (const guide of [USER_GUIDE, TECHNICAL_GUIDE]) {
      const en = guide.en.map((s) => s.id);
      expect(guide.es.map((s) => s.id)).toEqual(en);
      expect(new Set(en).size).toBe(en.length);
    }
  });
});

describe("HelpPage (task 37.6)", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("en");
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: { permissions: [] } });
  });

  it("lists every section in the index", () => {
    open("user");
    const index = screen.getByRole("navigation", { name: "Contents" });
    expect(within(index).getAllByRole("link")).toHaveLength(USER_GUIDE.en.length);
    expect(screen.getByRole("heading", { name: "Recovery codes" })).toBeInTheDocument();
  });

  it("searches without accents and highlights the matches", async () => {
    await i18n.changeLanguage("es");
    open("user");
    await userEvent.type(screen.getByPlaceholderText("Buscar en la guía"), "codigos recuperacion");
    expect(screen.getByRole("status")).toHaveTextContent(/coincide/);
    const section = document.getElementById("recovery-codes")!;
    expect(section).toBeInTheDocument();
    expect(within(section).getAllByText("códigos", { selector: "mark" }).length).toBeGreaterThan(0);
    expect(document.getElementById("private-mode")).toBeNull();
    await userEvent.clear(screen.getByPlaceholderText("Buscar en la guía"));
    await userEvent.type(screen.getByPlaceholderText("Buscar en la guía"), "zzzz");
    expect(screen.getByText("Ninguna sección coincide con la búsqueda.")).toBeInTheDocument();
  });

  it("copies a link to a section", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    open("user");
    await userEvent.click(screen.getByRole("button", { name: "Copy a link to “Locked account”" }));
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/help#locked`);
    expect(await screen.findByText("Link copied")).toBeInTheDocument();
  });

  it("shows the technical guide", () => {
    open("technical", "/help/technical");
    expect(screen.getByRole("heading", { name: "Technical guide", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "System parameters" })).toBeInTheDocument();
  });
});
