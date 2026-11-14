import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

/**
 * Minimal hCaptcha widget (Requirement 2.6, task 33.4).
 *
 * Loads https://js.hcaptcha.com/1/api.js once (explicit render) and renders
 * the checkbox challenge. No npm dependency: the official script is the only
 * code that runs the challenge.
 */

interface HCaptchaApi {
  render: (
    container: HTMLElement,
    params: {
      sitekey: string;
      hl?: string;
      callback: (token: string) => void;
      "expired-callback": () => void;
      "error-callback": () => void;
    }
  ) => string;
  reset: (widgetId?: string) => void;
  remove: (widgetId?: string) => void;
}

declare global {
  interface Window {
    hcaptcha?: HCaptchaApi;
  }
}

export const HCAPTCHA_SCRIPT_URL = "https://js.hcaptcha.com/1/api.js?render=explicit";

let scriptPromise: Promise<HCaptchaApi> | null = null;

function loadHCaptcha(): Promise<HCaptchaApi> {
  if (window.hcaptcha) return Promise.resolve(window.hcaptcha);
  if (!scriptPromise) {
    scriptPromise = new Promise<HCaptchaApi>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = HCAPTCHA_SCRIPT_URL;
      script.async = true;
      script.onload = () =>
        window.hcaptcha ? resolve(window.hcaptcha) : reject(new Error("hCaptcha missing"));
      script.onerror = () => {
        scriptPromise = null;
        reject(new Error("hCaptcha failed to load"));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

export interface HCaptchaHandle {
  /** Clear the solved challenge (tokens are single-use). */
  reset: () => void;
}

interface HCaptchaProps {
  siteKey: string;
  language?: string;
  /** Called with the token when solved, and with null when it expires or errors. */
  onToken: (token: string | null) => void;
  /** Called when the script cannot be loaded (blocked, offline). */
  onLoadError?: () => void;
}

const HCaptcha = forwardRef<HCaptchaHandle, HCaptchaProps>(function HCaptcha(
  { siteKey, language, onToken, onLoadError },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);
  // Latest callbacks without re-rendering the widget.
  const onTokenRef = useRef(onToken);
  const onLoadErrorRef = useRef(onLoadError);
  useEffect(() => {
    onTokenRef.current = onToken;
    onLoadErrorRef.current = onLoadError;
  });

  useImperativeHandle(ref, () => ({
    reset: () => {
      if (widgetId.current !== null) window.hcaptcha?.reset(widgetId.current);
      onTokenRef.current(null);
    },
  }));

  useEffect(() => {
    let cancelled = false;
    loadHCaptcha()
      .then((api) => {
        if (cancelled || !containerRef.current) return;
        widgetId.current = api.render(containerRef.current, {
          sitekey: siteKey,
          hl: language,
          callback: (token) => onTokenRef.current(token),
          "expired-callback": () => onTokenRef.current(null),
          "error-callback": () => onTokenRef.current(null),
        });
      })
      .catch(() => {
        if (!cancelled) onLoadErrorRef.current?.();
      });
    return () => {
      cancelled = true;
      if (widgetId.current !== null) {
        window.hcaptcha?.remove(widgetId.current);
        widgetId.current = null;
      }
    };
  }, [siteKey, language]);

  return <div ref={containerRef} data-testid="hcaptcha" className="flex justify-center" />;
});

export default HCaptcha;

/** Test helper. */
export function resetHCaptchaLoader(): void {
  scriptPromise = null;
}
