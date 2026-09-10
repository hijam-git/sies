import { Children, useState } from 'react';
import type { ReactNode } from 'react';
import { useT } from '../../lib/i18n';
import BaseModal from './BaseModal';

/**
 * The shell every filter row sits in.
 *
 * Not a clever component — a consistent one. The filters themselves differ
 * from screen to screen and should: a fee list narrows by class and month, a
 * staff list by designation. The frame around them should not.
 *
 * **On a phone, a row of more than two controls becomes a Filters button and a
 * sheet** (`CLAUDE.md` §7a). Four wrapped selects push the list itself below
 * the fold, so a clerk looking up a student's dues scrolls past the filters to
 * reach the answer every single time. Search stays on the bar, because it is
 * the control they actually reach for.
 */
export default function FilterBar({
  search,
  period,
  children,
  onClear,
  active = false,
}: {
  /** The search box, if the screen has one. Given the width it needs, and
   *  never moved into the sheet. */
  search?: ReactNode;
  /** A PeriodFilter, if the screen is time-bounded. */
  period?: ReactNode;
  /**
   * Selects, toggles — whatever else this screen filters by.
   *
   * These are rendered twice while the phone sheet is open (once on the bar,
   * hidden by CSS, once in the sheet), so give them `aria-label` rather than
   * `id` + `<label htmlFor>`: two elements with the same id is invalid, and
   * the label would point at whichever the browser found first.
   */
  children?: ReactNode;
  /** Shown only while something is actually filtering, so it is never a button
   *  that appears to do nothing. */
  onClear?: () => void;
  active?: boolean;
}) {
  const { t } = useT();
  const [sheetOpen, setSheetOpen] = useState(false);

  // `period` counts: it is a control the user operates like any other.
  const controlCount = Children.count(children) + (period ? 1 : 0);
  const collapses = controlCount > 2;

  const clearButton = onClear && active && (
    <button
      type="button"
      onClick={onClear}
      className="tap rounded-lg px-3 text-sm font-medium text-gray-500 hover:bg-gray-50 hover:text-gray-800"
    >
      {t('Clear filters')}
    </button>
  );

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-3 shadow-sm sm:p-4">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {/* The search box takes the room it needs and gives it back: grow so it
            fills a wide row, min-w-0 so it can shrink at 360px rather than
            pushing the rest of the row off the screen. */}
        {search && <div className="min-w-0 grow basis-full sm:basis-56">{search}</div>}

        {/* Phone: one button. From sm up the controls sit on the bar as usual. */}
        {collapses && (
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            className="tap gap-2 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 sm:hidden"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"
                 strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 4h18M6 12h12M10 20h4" />
            </svg>
            {t('Filter')}
            {active && <span className="h-2 w-2 rounded-full bg-blue-600" aria-hidden />}
          </button>
        )}

        <div className={`${collapses ? 'hidden sm:flex' : 'flex'} flex-wrap items-center gap-2 sm:gap-3`}>
          {period}
          {children}
        </div>

        <div className={collapses ? 'ml-auto hidden sm:block' : 'ml-auto'}>{clearButton}</div>
      </div>

      {collapses && (
        <BaseModal
          isOpen={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title={t('Filter')}
          footer={
            <div className="flex gap-2">
              {onClear && (
                <button
                  type="button"
                  onClick={() => { onClear(); setSheetOpen(false); }}
                  className="tap flex-1 rounded-lg border border-gray-200 px-4 text-sm font-medium text-gray-700"
                >
                  {t('Clear filters')}
                </button>
              )}
              <button
                type="button"
                onClick={() => setSheetOpen(false)}
                className="tap flex-1 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white"
              >
                {t('Close')}
              </button>
            </div>
          }
        >
          {/* Stacked and full-width: side-by-side selects on a 360px sheet are
              the problem this sheet exists to solve. */}
          <div className="flex flex-col gap-3 [&_select]:w-full [&>*]:w-full">
            {period}
            {children}
          </div>
        </BaseModal>
      )}
    </div>
  );
}

/** The one input style, so a search box is the same box on every screen. */
export const filterInputCls =
  'w-full rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-base text-gray-900 ' +
  'placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm';

/** The one select style. Matches filterInputCls so a row of mixed controls
 *  reads as one row rather than three widgets that happen to be adjacent.
 *  `min-h-[44px]` because a select is a touch target like any other. */
export const filterSelectCls =
  'min-h-[44px] rounded-lg border border-gray-200 bg-white px-3 py-2 text-base text-gray-900 ' +
  'focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm';
