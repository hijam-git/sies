import type { ReactNode } from 'react';

/**
 * The one form field.
 *
 * Every admin screen in every later phase draws the same thing: a label, a
 * control, an optional hint, and the field error the API sent back. Written
 * once so the eleventh screen does not invent a twelfth spacing.
 *
 * The control classes themselves live in `styles.ts` — a module that exports
 * both components and constants loses Fast Refresh for every file importing it.
 */
export default function Field({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  hint?: string;
  /** The message the API attached to this field, from `apiFieldErrors`. */
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block">
      {/* A label is a hint, not a heading: 13px from `sm` up and one line of
          gap, so the pair reads as one control rather than two rows. Stays
          14px on a phone, where the label is often the only context on screen. */}
      <span className="mb-1 block text-sm font-medium leading-tight text-gray-700 sm:text-[13px]">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </span>
      {children}
      {hint && !error && <span className="mt-0.5 block text-xs leading-snug text-gray-500">{hint}</span>}
      {error && <span className="mt-0.5 block text-xs font-medium leading-snug text-red-600">{error}</span>}
    </label>
  );
}

/**
 * The form grid: **one column on a phone**, two from `sm` up (`CLAUDE.md` §7a
 * rule 5). Side-by-side inputs at 360px leave two columns too narrow to type a
 * name into.
 *
 * Three columns from `lg`. These fields hold short values — a roll, a blood
 * group, a date — and one per row at 1280px turned twelve of them into nine
 * hundred pixels of scrolling. The row gap is tighter than the column gap
 * because vertical space is the scarce one.
 */
export function FieldGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>;
}

/** A field that needs the full width of the grid — an address, a long note. */
export function FieldWide({ children }: { children: ReactNode }) {
  return <div className="sm:col-span-2 lg:col-span-3">{children}</div>;
}

/** The red box above a form when the failure was not attached to one field. */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </div>
  );
}
