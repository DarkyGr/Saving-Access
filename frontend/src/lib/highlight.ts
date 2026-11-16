import { fold } from "./text";

/**
 * Ranges of *text* that match any word of *query*, ignoring case and accents
 * ("cafe" finds "Café"). Returned in order and never overlapping.
 */
export function matchRanges(text: string, query: string): [number, number][] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  // Fold character by character so positions map back to the original text.
  let folded = "";
  const origin: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const piece = fold(text[i]);
    for (const ch of piece) {
      folded += ch;
      origin.push(i);
    }
  }
  const ranges: [number, number][] = [];
  for (const word of words) {
    let from = folded.indexOf(word);
    while (from !== -1) {
      ranges.push([origin[from], origin[from + word.length - 1] + 1]);
      from = folded.indexOf(word, from + word.length);
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([...range]);
  }
  return merged;
}

/** *text* split into plain and matching pieces. */
export function splitMatches(text: string, query: string): { text: string; match: boolean }[] {
  const pieces: { text: string; match: boolean }[] = [];
  let at = 0;
  for (const [start, end] of matchRanges(text, query)) {
    if (start > at) pieces.push({ text: text.slice(at, start), match: false });
    pieces.push({ text: text.slice(start, end), match: true });
    at = end;
  }
  if (at < text.length) pieces.push({ text: text.slice(at), match: false });
  return pieces;
}
