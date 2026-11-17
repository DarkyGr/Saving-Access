/**
 * Password generator (Requirement 18, task 35.7).
 *
 * Uses the browser's cryptographic random source (crypto.getRandomValues)
 * with rejection sampling, so every character of a pool is equally likely.
 * The result has at least one character of every kind that is on, in random
 * positions. Nothing leaves the browser.
 */

export interface GeneratorOptions {
  length: number;
  lower: boolean;
  upper: boolean;
  digits: boolean;
  symbols: boolean;
  avoidSimilar: boolean;
}

export const MIN_LENGTH = 8;
export const MAX_LENGTH = 64;

export const DEFAULT_OPTIONS: GeneratorOptions = {
  length: 20,
  lower: true,
  upper: true,
  digits: true,
  symbols: true,
  avoidSimilar: true,
};

const POOLS = {
  lower: "abcdefghijklmnopqrstuvwxyz",
  upper: "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  digits: "0123456789",
  symbols: "!@#$%^&*()-_=+[]{};:,.?/~",
} as const;

// Characters that are easy to mistake for each other when read or typed.
const SIMILAR = new Set("Il1O0o");

type Kind = keyof typeof POOLS;
const KINDS: Kind[] = ["lower", "upper", "digits", "symbols"];

function pools(options: GeneratorOptions): string[] {
  return KINDS.filter((kind) => options[kind]).map((kind) =>
    options.avoidSimilar ? [...POOLS[kind]].filter((ch) => !SIMILAR.has(ch)).join("") : POOLS[kind]
  );
}

/** Uniform integer in [0, max) from crypto.getRandomValues (no modulo bias). */
export function randomBelow(max: number): number {
  if (max <= 0 || max > 2 ** 32) throw new RangeError("max out of range");
  const limit = Math.floor(2 ** 32 / max) * max;
  const buffer = new Uint32Array(1);
  for (;;) {
    crypto.getRandomValues(buffer);
    if (buffer[0] < limit) return buffer[0] % max;
  }
}

export function clampLength(length: number): number {
  if (!Number.isFinite(length)) return DEFAULT_OPTIONS.length;
  return Math.min(MAX_LENGTH, Math.max(MIN_LENGTH, Math.round(length)));
}

export function generatePassword(options: GeneratorOptions): string {
  const chosen = pools(options);
  if (chosen.length === 0) throw new Error("Choose at least one kind of character.");
  const length = clampLength(options.length);
  const all = chosen.join("");
  // One of each chosen kind, then the rest from all of them.
  const chars = chosen.map((pool) => pool[randomBelow(pool.length)]);
  while (chars.length < length) chars.push(all[randomBelow(all.length)]);
  // Fisher–Yates, so the guaranteed characters are not always first.
  for (let i = chars.length - 1; i > 0; i--) {
    const j = randomBelow(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}

/** Estimated strength: length × log2(characters available). */
export function strengthBits(options: GeneratorOptions): number {
  const size = pools(options).join("").length;
  return size > 0 ? Math.floor(clampLength(options.length) * Math.log2(size)) : 0;
}

export function strengthLevel(bits: number): "weak" | "good" | "strong" {
  return bits < 60 ? "weak" : bits < 90 ? "good" : "strong";
}
