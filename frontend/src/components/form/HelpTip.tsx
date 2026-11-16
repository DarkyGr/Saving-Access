import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { InfoIcon } from "../icons";

/**
 * The ⓘ next to a label (Requirement 13.5): help opens on hover, keyboard
 * focus or a tap, and closes on Escape, on leaving or on a tap elsewhere.
 * It sits outside the <label> so a tap never focuses the input instead.
 */
export default function HelpTip({ text, topic }: { text: string; topic: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onPointer = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  return (
    <span ref={rootRef} className="relative ml-1 inline-flex align-middle">
      <button
        type="button"
        aria-label={t("form.helpFor", { topic })}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        // Open, not toggle: a mouse click also fires hover and focus first.
        onClick={() => setOpen(true)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-gray-400 hover:text-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      >
        <InfoIcon className="h-4 w-4" />
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-1/2 top-full z-30 mt-1 w-64 -translate-x-1/2 rounded-md bg-gray-900 px-3 py-2 text-xs font-normal leading-snug text-white shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  );
}
