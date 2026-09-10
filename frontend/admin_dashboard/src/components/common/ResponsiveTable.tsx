import type { ReactNode } from 'react';

/**
 * One list, two shapes: a real `<table>` from `md` up, **stacked labelled
 * cards below it** (`CLAUDE.md` §7a rule 3).
 *
 * Solved once, here, because every list screen in every later phase has the
 * same problem. A five-column student row squeezed onto a 360px screen is
 * unreadable; the same row as a card with its fields labelled is fine. Doing
 * this per page guarantees eleven slightly different answers.
 *
 * Not for the genuinely grid-shaped screens — the attendance month register
 * and the marks grid keep their own layouts (§7a "the three hard screens"),
 * because a 31-column register is not a list of records.
 */

/**
 * The default `<td>` / `<th>` padding, and the only padding a column should
 * use. Exported so the handful of right-aligned columns can say
 * `${cellCls} text-right` instead of re-typing — and drift away from — the
 * numbers. `py-2` plus `h-11` on the row is a 44px single-line row.
 */
export const cellCls = 'px-3 py-2 text-left';
export const headCls = 'px-3 py-2 text-left';

/**
 * For a link or button that lives *inside* a cell — a guardian's phone number,
 * say. It still has to be 44px tall (§7a rule 4, and the office really does tap
 * it), but 44px of content inside a padded cell is a 60px row. The negative
 * margin lets the target overhang the cell's padding from `md` up, where the
 * row around it is exactly 44px anyway.
 */
export const cellTapCls = 'inline-flex min-h-[44px] items-center md:-my-2';

export interface Column<T> {
  /** Stable identity for React's key. Not the label: labels are translated. */
  key: string;
  /** Column heading, and the field label on the card. Already translated. */
  label: string;
  render: (row: T) => ReactNode;
  /**
   * The card's headline — the one field that identifies the row, drawn large
   * at the top with no label. Usually the name. Exactly one column should
   * carry it; the first one that does wins.
   */
  primary?: boolean;
  /**
   * Row actions and anything else that is not a field. Shown on the card in a
   * footer row rather than as a labelled line, because "Actions: ✎ 🗑" reads
   * as data the row contains.
   */
  action?: boolean;
  /** Padding and alignment for the `<td>`. Written out in full, never built
   *  from a variable — Tailwind only ships classes it can see in the source.
   *  Keep it as tight as the default: a column that pads itself back out is
   *  the one that sets the height of every row in the table. */
  cellClass?: string;
  /** Same, for the `<th>`. */
  headClass?: string;
  /**
   * Card-only: rendered in the card footer, never as a table column.
   *
   * For the "open this row" button. From `md` up the row itself is the
   * control, so a button repeating that in every row is 44px of noise; on a
   * card there is no hover and no pointer, and a tappable card with no visible
   * affordance is a guess (§7a rule 4).
   */
  cardOnly?: boolean;
  /** Hide below `lg` on the table too. For the columns that are context rather
   *  than content — a created-at date beside a name and an amount. */
  hideOnNarrow?: boolean;
}

export default function ResponsiveTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty,
  footer,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  /** Opens the record. On a card the whole card is the target, which is the
   *  only comfortable way to open a row with a thumb. */
  onRowClick?: (row: T) => void;
  /** What to show when there is nothing. Already translated. */
  empty: ReactNode;
  /** Pagination, usually. Sits below both shapes. */
  footer?: ReactNode;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
        {empty}
      </div>
    );
  }

  const primary = columns.find((c) => c.primary);
  const actions = columns.filter((c) => c.action);
  const fields = columns.filter((c) => c !== primary && !c.action);
  // The row is the control from md up; see `cardOnly`.
  const tableColumns = columns.filter((c) => !c.cardOnly);

  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm">
      {/* ── Cards: below md ────────────────────────────────────────────── */}
      <div className="divide-y divide-gray-100 md:hidden">
        {rows.map((row) => {
          const card = (
            <>
              {primary && (
                <div className="mb-2 text-base font-semibold text-gray-900">
                  {primary.render(row)}
                </div>
              )}
              <dl className="space-y-1.5">
                {fields.map((c) => (
                  <div key={c.key} className="flex items-start justify-between gap-3">
                    <dt className="shrink-0 text-xs uppercase tracking-wide text-gray-400">
                      {c.label}
                    </dt>
                    <dd className="min-w-0 text-right text-sm text-gray-900">{c.render(row)}</dd>
                  </div>
                ))}
              </dl>
              {actions.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-gray-50 pt-3">
                  {actions.map((c) => (
                    <span key={c.key}>{c.render(row)}</span>
                  ))}
                </div>
              )}
            </>
          );

          // A <button> wrapper would swallow the action controls inside it —
          // nested interactive elements are invalid and the inner click never
          // fires. A div with a role keeps both working.
          return onRowClick ? (
            <div
              key={rowKey(row)}
              role="button"
              tabIndex={0}
              onClick={() => onRowClick(row)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onRowClick(row);
                }
              }}
              className="cursor-pointer p-4 text-left transition-colors first:rounded-t-xl last:rounded-b-xl hover:bg-gray-50"
            >
              {card}
            </div>
          ) : (
            <div key={rowKey(row)} className="p-4">
              {card}
            </div>
          );
        })}
      </div>

      {/* ── Table: md and up ───────────────────────────────────────────── */}
      {/* scroll-x so a wide table scrolls inside this card rather than widening
          the page — the body never scrolls sideways (§7a rule 1). */}
      <div className="scroll-x hidden md:block">
        <table className="min-w-full">
          <thead>
            <tr className="border-b border-gray-100">
              {tableColumns.map((c) => (
                <th
                  key={c.key}
                  className={`${c.headClass ?? headCls} text-[11px] font-semibold uppercase tracking-wide text-gray-500 ${
                    c.hideOnNarrow ? 'hidden lg:table-cell' : ''
                  }`}
                >
                  {c.action ? <span className="sr-only">{c.label}</span> : c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row) => (
              // The row IS the control from md up, so the per-row "open" button
              // can go. h-11 rather than fatter padding: 44px is both the touch
              // floor the row now has to meet as a target itself (§7a rule 4)
              // and about as short as a line of Bangla can be set without
              // crowding its descenders.
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                role={onRowClick ? 'button' : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                className={`h-11 ${
                  onRowClick
                    ? 'cursor-pointer transition-colors hover:bg-gray-50 focus-visible:bg-blue-50 focus-visible:outline-none'
                    : ''
                }`}
              >
                {tableColumns.map((c) => (
                  <td
                    key={c.key}
                    className={`${c.cellClass ?? cellCls} text-sm text-gray-900 ${
                      c.hideOnNarrow ? 'hidden lg:table-cell' : ''
                    }`}
                  >
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {footer}
    </div>
  );
}
