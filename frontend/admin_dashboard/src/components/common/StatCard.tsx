import type { ReactNode } from 'react';

/**
 * The dashboard's one stat card: an 11px label with a small tinted glyph, one
 * big number, and an optional divided footer for the detail.
 *
 * Shared rather than copied because adjacent screens drawing their numbers in
 * two different card styles read as two different products.
 */
export default function StatCard({
  tone,
  icon,
  label,
  value,
  sub,
  footer,
  valueCls,
}: {
  tone: 'blue' | 'green' | 'amber' | 'red' | 'gray';
  icon: ReactNode;
  label: string;
  value: string | number;
  /** One short line under the number. Say it only when it is worth saying. */
  sub?: string;
  valueCls?: string;
  /** `hint` explains a figure whose one-word label cannot. Plain title text, so
   *  it costs no layout — the label must still stand alone on a phone, where
   *  nothing hovers. */
  footer?: { label: string; value: string | number; cls?: string; hint?: string }[];
}) {
  const tint = {
    blue: { ink: 'text-blue-600' },
    green: { ink: 'text-emerald-600' },
    amber: { ink: 'text-amber-600' },
    red: { ink: 'text-red-600' },
    gray: { ink: 'text-gray-600' },
  }[tone];

  return (
    // h-full + flex-col: the grid stretches every card to the tallest in the
    // row, and mt-auto on the footer pushes it to the bottom of that height
    // instead of leaving it floating mid-card beside a taller neighbour.
    <div className="flex h-full flex-col rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
      {/* Label and icon on one line above the figure, rather than a 40px tinted
          square beside a two-line stack. The square was the tallest thing on a
          card whose whole job is to show one number, and the number is what the
          eye is looking for — so the number is what gets the size. */}
      <div className={footer && footer.length > 0 ? 'mb-2' : ''}>
        <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase leading-tight tracking-wide text-gray-500">
          <span className={`flex-none ${tint.ink}`}>{icon}</span>
          <span className="min-w-0 truncate">{label}</span>
        </p>
        {/* A taka total is long — ৳১,৮৪,২০০ in a half-width card on a phone.
            Truncating hides the very thing the card is for, so it steps down
            a size on small screens instead. */}
        <p className={`mt-1 truncate text-xl font-bold leading-none sm:text-2xl ${valueCls || 'text-gray-900'}`}>
          {value}
        </p>
        {sub && <p className="mt-1 text-[11px] leading-snug text-gray-400">{sub}</p>}
      </div>

      {/* Static class names in the ternary — Tailwind cannot see an
          interpolated one like grid-cols-{n}. */}
      {footer && footer.length > 0 && (
        <div
          className={`mt-auto grid border-t border-gray-50 pt-2 ${
            footer.length >= 4
              ? 'grid-cols-4 gap-1'
              : footer.length === 3
                ? 'grid-cols-3 gap-2'
                : footer.length === 2
                  ? 'grid-cols-2 gap-2'
                  : 'grid-cols-1 gap-2'
          }`}
        >
          {footer.map((f, i) => (
            <div
              key={f.label}
              title={f.hint}
              /* A rule before every cell but the first, so four columns read as
                 four and not as one run of numbers. Only from three up. */
              className={`min-w-0 text-center ${
                i > 0 && footer.length >= 3 ? 'border-l border-gray-100' : ''
              }`}
            >
              <p className={`truncate text-sm font-semibold leading-tight sm:text-base ${f.cls || 'text-gray-700'}`}>
                {f.value}
              </p>
              {/* At four across the label gets a quarter of the card, so it
                  wraps instead of truncating: two short lines say what one
                  clipped line cannot. */}
              <p
                className={`mt-0.5 text-[11px] leading-tight text-gray-400 ${
                  footer.length >= 4 ? 'break-words' : 'truncate'
                }`}
              >
                {f.label}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Heroicons-style stroked path, sized to sit on the card's label line. */
export function StatIcon({ d }: { d: string }) {
  return (
    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />
    </svg>
  );
}
