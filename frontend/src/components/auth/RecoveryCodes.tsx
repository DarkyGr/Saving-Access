import { useState } from "react";
import { useTranslation } from "react-i18next";

/**
 * The 10 recovery codes, shown once (Requirement 16.1): copy, download as a
 * text file, and a confirmation that they were saved before going on.
 */
export default function RecoveryCodes({ codes, onDone, doneLabel }: { codes: string[]; onDone: () => void; doneLabel: string }) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([`Save-Pass\n\n${text}\n`], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "save-pass-recovery-codes.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-gray-700">{t("twoFactor.codesIntro")}</p>
      <ol aria-label={t("twoFactor.codesTitle")} className="grid grid-cols-2 gap-2 rounded-md border border-gray-200 bg-gray-50 p-4 font-mono text-sm text-gray-900">
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => void copy()} className="min-h-[44px] rounded-md border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50">
          {copied ? t("twoFactor.copied") : t("twoFactor.copy")}
        </button>
        <button type="button" onClick={download} className="min-h-[44px] rounded-md border border-gray-300 px-4 text-sm font-medium text-gray-700 hover:bg-gray-50">
          {t("twoFactor.download")}
        </button>
      </div>
      <label className="flex items-start gap-2 text-sm text-gray-700">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className="mt-0.5 h-4 w-4" />
        {t("twoFactor.savedThem")}
      </label>
      <button
        type="button"
        onClick={onDone}
        disabled={!saved}
        className="min-h-[44px] rounded-md bg-indigo-600 px-4 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {doneLabel}
      </button>
    </div>
  );
}
