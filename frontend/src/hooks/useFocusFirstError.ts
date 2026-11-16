import { useEffect, useRef, useState, type RefObject } from "react";

/**
 * After a submit that failed validation, move focus to the first field marked
 * `aria-invalid="true"` and scroll it into view (Requirement 13.5).
 *
 * Only a failed submit triggers it — not clearing an error while typing, so
 * focus never jumps away from the field being corrected.
 */
export function useFocusFirstError(formRef: RefObject<HTMLFormElement | null>): () => void {
  const [attempt, setAttempt] = useState(0);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const field = formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]');
    if (field) {
      field.focus();
      field.scrollIntoView?.({ block: "center", behavior: "smooth" });
    }
  }, [attempt, formRef]);

  return () => setAttempt((n) => n + 1);
}
