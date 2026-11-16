import type { ReactNode } from "react";

/**
 * The 12 built-in avatars (original line drawings, task 37.3) and the avatar
 * shown for a person: uploaded picture → built-in icon → initials.
 */
export const AVATAR_PRESETS = [
  "key", "shield", "lock", "star", "sun", "moon", "leaf", "wave", "mountain", "rocket", "heart", "bolt",
] as const;
export type AvatarPreset = (typeof AVATAR_PRESETS)[number];

const DRAWINGS: Record<AvatarPreset, { bg: string; path: ReactNode }> = {
  key: { bg: "#4f46e5", path: <><circle cx="8" cy="15" r="4" /><path d="m11 12 8-8M16 7l3 3" /></> },
  shield: { bg: "#059669", path: <path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z" /> },
  lock: { bg: "#7c3aed", path: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></> },
  star: { bg: "#d97706", path: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z" /> },
  sun: { bg: "#ea580c", path: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></> },
  moon: { bg: "#1e3a8a", path: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" /> },
  leaf: { bg: "#16a34a", path: <><path d="M5 19c0-8 6-14 15-14 0 9-6 15-14 15" /><path d="M5 19 13 11" /></> },
  wave: { bg: "#0284c7", path: <path d="M2 12c2.5-3 5-3 7.5 0s5 3 7.5 0 5-3 5-3M2 17c2.5-3 5-3 7.5 0s5 3 7.5 0 5-3 5-3" /> },
  mountain: { bg: "#475569", path: <path d="m3 20 6-10 4 6 2-3 6 7z" /> },
  rocket: { bg: "#db2777", path: <><path d="M12 15c-2-1-3-3-3-3s1-7 6-9c1 5-1 8-3 9z" /><path d="M9 12 6 13l-1 4 4-1M12 15l-1 3 4-1 1-3" /></> },
  heart: { bg: "#e11d48", path: <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" /> },
  bolt: { bg: "#ca8a04", path: <path d="M13 2 4 14h7l-1 8 9-12h-7z" /> },
};

export function PresetIcon({ preset, className = "h-full w-full" }: { preset: AvatarPreset; className?: string }) {
  const d = DRAWINGS[preset];
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true" focusable="false">
      <rect width="24" height="24" rx="12" fill={d.bg} />
      <g transform="translate(4.8 4.8) scale(0.6)" fill="none" stroke="#fff" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
        {d.path}
      </g>
    </svg>
  );
}

const SIZES = { sm: "h-8 w-8 text-sm", md: "h-10 w-10 text-base", lg: "h-20 w-20 text-2xl" };

export default function Avatar({
  name,
  preset,
  imageUrl,
  size = "sm",
}: {
  name: string;
  preset?: string | null;
  imageUrl?: string | null;
  size?: keyof typeof SIZES;
}) {
  const box = `${SIZES[size]} shrink-0 overflow-hidden rounded-full`;
  if (imageUrl) {
    return <img src={imageUrl} alt="" className={`${box} object-cover`} />;
  }
  if (preset && (AVATAR_PRESETS as readonly string[]).includes(preset)) {
    return (
      <span aria-hidden="true" className={`${box} inline-flex`}>
        <PresetIcon preset={preset as AvatarPreset} />
      </span>
    );
  }
  const initials = name.trim().split(/\s+/).map((w) => w[0]).join("").slice(0, 2) || "?";
  return (
    <span aria-hidden="true" className={`${box} flex items-center justify-center bg-indigo-600 font-semibold uppercase text-white`}>
      {initials}
    </span>
  );
}
