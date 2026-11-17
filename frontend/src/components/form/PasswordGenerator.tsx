import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  DEFAULT_OPTIONS,
  MAX_LENGTH,
  MIN_LENGTH,
  clampLength,
  generatePassword,
  strengthBits,
  strengthLevel,
  type GeneratorOptions,
} from "../../lib/passwordGenerator";
import { readLocal, writeLocal } from "../../lib/storage";

// Only the options are remembered on the device, never a password.
const OPTIONS_KEY = "savepass-generator-options";

const LEVEL_STYLE = {
  weak: "text-red-600",
  good: "text-amber-700",
  strong: "text-green-700",
} as const;

function savedOptions(): GeneratorOptions {
  const saved = readLocal<Partial<GeneratorOptions>>(OPTIONS_KEY, {});
  const merged = { ...DEFAULT_OPTIONS, ...saved };
  return { ...merged, length: clampLength(Number(merged.length)) };
}

/**
 * Password generator under a credential's password field (Requirement 18,
 * task 35.7). Closed until asked for; "Use this password" fills the field.
 */
export default function PasswordGenerator({ onUse }: { onUse: (password: string) => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<GeneratorOptions>(savedOptions);
  const [password, setPassword] = useState("");
  const panelId = useId();
  const lengthId = useId();
  const anyKind = options.lower || options.upper || options.digits || options.symbols;

  useEffect(() => {
    if (!open) return;
    writeLocal(OPTIONS_KEY, options);
    setPassword(anyKind ? generatePassword(options) : "");
  }, [open, options, anyKind]);

  function set<K extends keyof GeneratorOptions>(key: K, value: GeneratorOptions[K]) {
    setOptions((current) => ({ ...current, [key]: value }));
  }

  const bits = anyKind ? strengthBits(options) : 0;
  const level = strengthLevel(bits);

  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="text-sm font-medium text-indigo-600 hover:text-indigo-500"
      >
        {open ? t("generator.hide") : t("generator.open")}
      </button>

      {open && (
        <div id={panelId} role="group" aria-label={t("generator.title")} className="mt-2 rounded-md border border-gray-200 bg-gray-50 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <output
              aria-label={t("generator.generated")}
              data-testid="generated-password"
              className="min-h-[44px] flex-1 break-all rounded border border-gray-300 bg-white px-3 py-2 font-mono text-sm text-gray-900"
            >
              {password || "—"}
            </output>
            <button
              type="button"
              onClick={() => anyKind && setPassword(generatePassword(options))}
              disabled={!anyKind}
              className="min-h-[44px] rounded-md border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {t("generator.again")}
            </button>
          </div>

          <p className={`mt-2 text-xs font-medium ${anyKind ? LEVEL_STYLE[level] : "text-red-600"}`} aria-live="polite">
            {anyKind ? t(`generator.strength.${level}`, { bits }) : t("generator.chooseOne")}
          </p>

          <div className="mt-3 flex items-center gap-3">
            <label htmlFor={lengthId} className="text-sm text-gray-700">
              {t("generator.length")}
            </label>
            <input
              id={lengthId}
              type="range"
              min={MIN_LENGTH}
              max={MAX_LENGTH}
              value={options.length}
              onChange={(e) => set("length", clampLength(Number(e.target.value)))}
              className="flex-1"
            />
            <span className="w-8 text-right font-mono text-sm text-gray-900">{options.length}</span>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-gray-700 sm:grid-cols-3">
            {(["lower", "upper", "digits", "symbols", "avoidSimilar"] as const).map((key) => (
              <label key={key} className="flex items-center gap-2">
                <input type="checkbox" checked={options[key]} onChange={(e) => set(key, e.target.checked)} className="h-4 w-4" />
                {t(`generator.${key}`)}
              </label>
            ))}
          </div>

          <button
            type="button"
            disabled={!password}
            onClick={() => {
              onUse(password);
              setOpen(false);
            }}
            className="mt-4 min-h-[44px] rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {t("generator.use")}
          </button>
        </div>
      )}
    </div>
  );
}
