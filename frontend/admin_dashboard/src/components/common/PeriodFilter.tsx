import { useState } from 'react';
import { useT } from '../../lib/i18n';
import { dateOffsetInDhaka, todayInDhaka, currentMonthInDhaka } from '../../lib/timezone';
import { lastDays, lastMonth, periodLabel, thisMonth } from '../../lib/period';
import type { Period } from '../../lib/period';

/**
 * The one date-range control.
 *
 * Every screen in this system is time-bounded — a month's fees, a month's
 * attendance, a term's marks — and somebody who learns the period control on
 * the fee screen must not have to learn it again on attendance. One control,
 * one shape of answer (`lib/period.ts`).
 *
 * All the dates are computed in **Asia/Dhaka**, not the browser's zone.
 * "Today" on a laptop still set to UTC would be yesterday's register for the
 * first six hours of every Bangladeshi morning — which is exactly when
 * attendance is taken.
 */

type PresetKey = 'today' | 'last7' | 'last30' | 'this_month' | 'last_month' | 'all' | 'custom';

export default function PeriodFilter({
  value,
  onChange,
  allowAllTime = false,
  allTimeLabel,
  className = '',
}: {
  value: Period;
  onChange: (p: Period) => void;
  /** Only where an unbounded view means something: "every payment this student
   *  ever made" is a real question; "a month's attendance, ever" is not. */
  allowAllTime?: boolean;
  allTimeLabel?: string;
  className?: string;
}) {
  const { t } = useT();

  /** Whether the user asked to pick the dates themselves.
   *
   *  This has to be state rather than inferred from the value. Choosing
   *  "Choose dates" seeds the last week so the boxes are never empty — but
   *  last-week IS a preset, so an inferred control would decide it was showing
   *  "Last 7 days" the moment the seed landed, snap the dropdown back, and hide
   *  the date boxes it had just opened. */
  const [customOpen, setCustomOpen] = useState(false);

  const shiftMonth = (by: number) => {
    if (value.mode !== 'month') return;
    let m = value.month + by;
    let y = value.year;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    onChange({ mode: 'month', year: y, month: m });
  };

  const applyPreset = (key: PresetKey) => {
    setCustomOpen(key === 'custom');
    switch (key) {
      case 'today':
        return onChange({ mode: 'range', from: todayInDhaka(), to: todayInDhaka() });
      case 'last7':
        return onChange(lastDays(7));
      case 'last30':
        return onChange(lastDays(30));
      case 'this_month':
        return onChange(thisMonth());
      case 'last_month':
        return onChange(lastMonth());
      case 'all':
        return onChange({ mode: 'all' });
      case 'custom':
        // Seeded with the last week so the boxes are never both empty — a
        // half-filled range silently falls back to the month, which looks like
        // the control was ignored.
        return onChange(lastDays(7));
    }
  };

  /** Which preset the current value corresponds to, so the dropdown shows what
   *  is actually on screen rather than resetting to a default. */
  const currentPreset = (): PresetKey => {
    if (value.mode === 'all') return 'all';
    if (value.mode === 'month') {
      const now = currentMonthInDhaka();
      return value.year === now.year && value.month === now.month ? 'this_month' : 'last_month';
    }
    // Asked-for beats looks-like: once the editor is open it stays open, even
    // while the dates being typed pass through a preset — otherwise the boxes
    // vanish under the user mid-edit.
    if (customOpen) return 'custom';
    if (value.from === todayInDhaka() && value.to === todayInDhaka()) return 'today';
    if (value.from === dateOffsetInDhaka(-6) && value.to === todayInDhaka()) return 'last7';
    if (value.from === dateOffsetInDhaka(-29) && value.to === todayInDhaka()) return 'last30';
    return 'custom';
  };

  const controlCls =
    'min-h-[44px] w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-base ' +
    'text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:w-auto sm:text-sm';

  return (
    // Stacks at 360px, sits on one line from sm up.
    <div className={`flex w-full flex-wrap items-center gap-2 sm:w-auto ${className}`}>
      <select
        aria-label={t('Period')}
        value={currentPreset()}
        onChange={(e) => applyPreset(e.target.value as PresetKey)}
        className={controlCls}
      >
        <option value="today">{t('Today')}</option>
        <option value="last7">{t('Last 7 days')}</option>
        <option value="last30">{t('Last 30 days')}</option>
        <option value="this_month">{t('This month')}</option>
        <option value="last_month">{t('Last month')}</option>
        {allowAllTime && <option value="all">{allTimeLabel || t('All time')}</option>}
        <option value="custom">{t('Choose dates')}</option>
      </select>

      {/* Stepping months by arrow is the nicest thing about this control, and on
          a phone it is far quicker than reopening the dropdown. Month mode
          only, where it means something. */}
      {value.mode === 'month' && (
        <div className="flex w-full items-center gap-1 rounded-lg bg-gray-100 p-1 sm:w-auto">
          <button
            type="button"
            onClick={() => shiftMonth(-1)}
            aria-label={t('Previous month')}
            className="tap rounded-md text-gray-500 hover:bg-white hover:text-gray-900"
          >
            ←
          </button>
          <span className="flex-1 px-1 text-center text-sm font-medium text-gray-900 sm:min-w-[7.5rem] sm:flex-none">
            {periodLabel(value, t)}
          </span>
          <button
            type="button"
            onClick={() => shiftMonth(1)}
            aria-label={t('Next month')}
            className="tap rounded-md text-gray-500 hover:bg-white hover:text-gray-900"
          >
            →
          </button>
        </div>
      )}

      {value.mode === 'range' && currentPreset() === 'custom' && (
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
          <input
            type="date"
            aria-label={t('From')}
            value={value.from}
            max={value.to || undefined}
            onChange={(e) => onChange({ ...value, from: e.target.value })}
            className={controlCls}
          />
          <span className="hidden text-sm text-gray-400 sm:inline">→</span>
          <input
            type="date"
            aria-label={t('To')}
            value={value.to}
            min={value.from || undefined}
            onChange={(e) => onChange({ ...value, to: e.target.value })}
            className={controlCls}
          />
        </div>
      )}
    </div>
  );
}
