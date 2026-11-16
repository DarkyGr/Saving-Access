/** Lower case without accents: "Árbol" → "arbol" (search ignores both). */
export function fold(value: string): string {
  return value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** True when every word of *query* appears in one of *fields*. */
export function matchesQuery(query: string, fields: readonly string[]): boolean {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = fields.map(fold).join(" ");
  return words.every((w) => haystack.includes(w));
}
