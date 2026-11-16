import { useEffect, useMemo, useState } from "react";

export const PAGE_SIZES = [10, 20, 30, 50, 100] as const;

/**
 * Client-side pagination (Requirement 13.4). Changing *resetKey* (filters,
 * search, view) goes back to page 1; the page is clamped when the list
 * shrinks (for example after a delete).
 */
export function usePaged<T>(items: readonly T[], defaultSize: number, resetKey: string) {
  const [pageSize, setPageSizeState] = useState(defaultSize);
  const [page, setPage] = useState(1);

  useEffect(() => setPage(1), [resetKey]);
  useEffect(() => setPageSizeState(defaultSize), [defaultSize]);

  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(page, pages);

  const pageItems = useMemo(
    () => items.slice((current - 1) * pageSize, current * pageSize),
    [items, current, pageSize]
  );

  return {
    page: current,
    pages,
    pageSize,
    total,
    from: total === 0 ? 0 : (current - 1) * pageSize + 1,
    to: Math.min(current * pageSize, total),
    pageItems,
    setPage,
    setPageSize: (size: number) => {
      setPageSizeState(size);
      setPage(1);
    },
  };
}

export type Paged<T> = ReturnType<typeof usePaged<T>>;
