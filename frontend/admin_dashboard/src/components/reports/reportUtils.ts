import type { Period } from '../../lib/period';

/**
 * The arithmetic behind the report screens (`docs/02` §4.8).
 *
 * Two rules everything here obeys:
 *
 * **1. Money is summed in poisha, as integers.** The API sends every amount as
 * a decimal STRING precisely so that no figure passes through a float, and a
 * report that adds those with `+` throws that away — `0.1 + 0.2` is the reason
 * a collection sheet ends in `.00000000004`. So amounts are parsed to integer
 * poisha, added as integers, and turned back into a decimal string at the end.
 *
 * **2. Periods are applied here, not by the API.** None of the list endpoints
 * these reports read has a date-range filter — `fees`, `payments`, `income`,
 * `expenses` and `admissions` all filter on exact fields only. Until they gain
 * one, the rows are fetched and narrowed here, which is honest but bounded:
 * `listAll` stops at 2,000 rows.
 */

/** `"1250.50"` → `125050`. Anything unparseable is zero, never NaN. */
export function poisha(amount: string | number | null | undefined): number {
  if (amount === null || amount === undefined || amount === '') return 0;
  const text = String(amount).trim();
  const negative = text.startsWith('-');
  const [whole = '0', fraction = ''] = text.replace('-', '').split('.');
  const value = Number(whole) * 100 + Number((fraction + '00').slice(0, 2));
  return Number.isFinite(value) ? (negative ? -value : value) : 0;
}

/** `125050` → `"1250.50"` — back to the shape the rest of the app formats. */
export function taka(value: number): string {
  const sign = value < 0 ? '-' : '';
  const absolute = Math.abs(Math.round(value));
  return `${sign}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`;
}

export function sumPoisha(amounts: (string | number | null | undefined)[]): number {
  return amounts.reduce<number>((total, amount) => total + poisha(amount), 0);
}

/** The inclusive `[from, to]` this period covers, or null for all time. */
export function periodRange(period: Period): { from: string; to: string } | null {
  if (period.mode === 'all') return null;
  if (period.mode === 'range') return { from: period.from, to: period.to };
  const last = new Date(Date.UTC(period.year, period.month, 0)).getUTCDate();
  const month = String(period.month).padStart(2, '0');
  return {
    from: `${period.year}-${month}-01`,
    to: `${period.year}-${month}-${String(last).padStart(2, '0')}`,
  };
}

/**
 * Is this timestamp inside the period?
 *
 * Compared as the first ten characters — the ISO date — and not as `Date`
 * objects: `paid_at` is a timestamp WITH an offset (`+06:00`), and parsing it
 * into a browser Date moves a payment taken at 11pm in Dhaka into the previous
 * day for anybody whose laptop is set to UTC. The date the office means is the
 * one in the string.
 */
export function inPeriod(
  timestamp: string | null | undefined,
  range: { from: string; to: string } | null,
): boolean {
  if (!range) return true;
  if (!timestamp) return false;
  const day = timestamp.slice(0, 10);
  return day >= range.from && day <= range.to;
}

/** `groupBy(rows, r => r.category_name)` → `Map<key, rows>`, insertion-ordered. */
export function groupBy<T, K>(rows: T[], key: (row: T) => K): Map<K, T[]> {
  const out = new Map<K, T[]>();
  rows.forEach((row) => {
    const k = key(row);
    out.set(k, [...(out.get(k) ?? []), row]);
  });
  return out;
}

/** `"2026-03-14T…"` → `"2026-03"`. The month a row belongs to, for grouping. */
export function monthOf(timestamp: string | null | undefined): string {
  return (timestamp ?? '').slice(0, 7);
}

/** A share as a fraction, with the empty denominator answering null rather than
 *  NaN — a class with nobody in it has no attendance percentage, and printing
 *  `0%` for it would read as everybody absent. */
export function share(part: number, whole: number): number | null {
  return whole > 0 ? part / whole : null;
}
