import { dateOffsetInDhaka, todayInDhaka, currentMonthInDhaka } from './timezone';

/**
 * The shape of "which period am I looking at", and the three things every
 * screen does with it.
 *
 * Separate from the `PeriodFilter` component that edits it, because the answer
 * outlives the control: a page holds a `Period` in state, sends
 * `periodParams()` to the API and prints `periodLabel()` in its heading long
 * before and after the filter row is on screen.
 *
 * It speaks the backend's own contract: a month as `year` + `month`, a range as
 * `from` + `to` with `to` INCLUSIVE, and all-time as no period at all.
 */
export type Period =
  | { mode: 'month'; year: number; month: number }
  | { mode: 'range'; from: string; to: string }
  | { mode: 'all' };

export const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;

export function thisMonth(): Period {
  const { year, month } = currentMonthInDhaka();
  return { mode: 'month', year, month };
}

export function lastMonth(): Period {
  const { year, month } = currentMonthInDhaka();
  return month === 1
    ? { mode: 'month', year: year - 1, month: 12 }
    : { mode: 'month', year, month: month - 1 };
}

/** The last `days` days, today inclusive. */
export function lastDays(days: number): Period {
  return { mode: 'range', from: dateOffsetInDhaka(-(days - 1)), to: todayInDhaka() };
}

/** The query parameters for this period — exactly what the API reads. */
export function periodParams(p: Period): Record<string, string> {
  if (p.mode === 'all') return { all: '1' };
  if (p.mode === 'range') return { from: p.from, to: p.to };
  return { year: String(p.year), month: String(p.month) };
}

/** A short human label, for headings that say what they are showing. */
export function periodLabel(p: Period, t: (s: string) => string): string {
  if (p.mode === 'all') return t('All time');
  if (p.mode === 'range') return p.from === p.to ? p.from : `${p.from} → ${p.to}`;
  return `${t(MONTHS[p.month - 1])} ${p.year}`;
}
