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
      <span className="mb-1 block text-sm font-medium text-gray-700">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-gray-500">{hint}</span>}
      {error && <span className="mt-1 block text-xs font-medium text-red-600">{error}</span>}
    </label>
  );
}

/**
 * The form grid: **one column on a phone**, two from `sm` up (`CLAUDE.md` §7a
 * rule 5). Side-by-side inputs at 360px leave two columns too narrow to type a
 * name into.
 */
export function FieldGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</div>;
}

/** A field that needs the full width of the grid — an address, a long note. */
export function FieldWide({ children }: { children: ReactNode }) {
  return <div className="sm:col-span-2">{children}</div>;
}

/** The red box above a form when the failure was not attached to one field. */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {message}
    </div>
  );
}
