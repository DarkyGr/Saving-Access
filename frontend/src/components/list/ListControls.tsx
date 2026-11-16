import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { Paged } from "../../hooks/usePaged";
import { PAGE_SIZES } from "../../hooks/usePaged";
import type { ListView } from "../../hooks/useListView";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  GridIcon,
  ListIcon,
  SearchIcon,
} from "../icons";

const control =
  "block rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 " +
  "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 min-h-[44px] md:min-h-[40px]";

/** Search box: accent- and case-insensitive (the filtering is the caller's). */
export function SearchBox({
  id,
  value,
  onChange,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <div className="relative w-full sm:max-w-sm">
      <label htmlFor={id} className="sr-only">
        {placeholder}
      </label>
      <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        id={id}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className={`${control} w-full pl-9 placeholder-gray-400`}
      />
    </div>
  );
}

/** A filter select whose first option is "All". Options are sorted A–Z. */
export function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  const { t, i18n } = useTranslation();
  const sorted = [...options].sort((a, b) => a.label.localeCompare(b.label, i18n.language));
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-sm text-gray-600 whitespace-nowrap">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={control}>
        <option value="">{t("list.all")}</option>
        {sorted.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Two-icon list / grid switch (saved in the account by useListView). */
export function ViewToggle({ view, onChange }: { view: ListView; onChange: (view: ListView) => void }) {
  const { t } = useTranslation();
  const button = (value: ListView, label: string, icon: ReactNode) => (
    <button
      type="button"
      onClick={() => onChange(value)}
      aria-pressed={view === value}
      aria-label={label}
      title={label}
      className={[
        "flex h-10 w-10 items-center justify-center",
        view === value ? "bg-indigo-50 text-indigo-700" : "bg-white text-gray-500 hover:bg-gray-50",
      ].join(" ")}
    >
      {icon}
    </button>
  );
  return (
    <div className="inline-flex shrink-0 overflow-hidden rounded-md border border-gray-300" role="group" aria-label={t("list.viewLabel")}>
      {button("list", t("list.viewList"), <ListIcon />)}
      {button("grid", t("list.viewGrid"), <GridIcon />)}
    </div>
  );
}

/** Search and filters wrap on the left; the view switch stays on the right. */
export function ListToolbar({ children, view }: { children: ReactNode; view?: ReactNode }) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">{children}</div>
      {view}
    </div>
  );
}

/** "1–10 of 42", first / previous / next / last and the page size. */
export function Pagination<T>({ paged, id }: { paged: Paged<T>; id: string }) {
  const { t } = useTranslation();
  if (paged.total === 0) return null;
  const nav = (label: string, target: number, disabled: boolean, icon: ReactNode) => (
    <button
      type="button"
      onClick={() => paged.setPage(target)}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="flex h-10 w-10 items-center justify-center rounded-md text-gray-600 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {icon}
    </button>
  );
  return (
    <div className="mt-4 flex flex-col-reverse gap-3 text-sm text-gray-600 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2">
        <label htmlFor={`${id}-size`}>{t("list.perPage")}</label>
        <select
          id={`${id}-size`}
          value={paged.pageSize}
          onChange={(e) => paged.setPageSize(Number(e.target.value))}
          className={control}
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-1">
        <span className="mr-2 tabular-nums" aria-live="polite">
          {t("list.range", { from: paged.from, to: paged.to, total: paged.total })}
        </span>
        {nav(t("list.first"), 1, paged.page === 1, <ChevronsLeftIcon />)}
        {nav(t("list.previous"), paged.page - 1, paged.page === 1, <ChevronLeftIcon />)}
        {nav(t("list.next"), paged.page + 1, paged.page === paged.pages, <ChevronRightIcon />)}
        {nav(t("list.last"), paged.pages, paged.page === paged.pages, <ChevronsRightIcon />)}
      </div>
    </div>
  );
}
