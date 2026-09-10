/**
 * Dates, in Asia/Dhaka.
 *
 * Every institution on the platform is in Bangladesh, so the zone is hard-coded
 * and matches the backend's `TIME_ZONE`. The API returns UTC ISO 8601; these
 * convert for display.
 *
 * Uses the native `Intl.DateTimeFormat` — no date library, which is one fewer
 * dependency and one fewer thing to keep patched.
 */

export const DHAKA_TZ = 'Asia/Dhaka';

/** `"12 Sep 2026, 02:30 pm"` — a timestamp on an activity row or a receipt. */
export function formatDhakaDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: DHAKA_TZ,
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }).format(new Date(iso));
  } catch {
    // An unparseable value is shown as it came rather than as "Invalid Date" —
    // the raw string is at least a clue to whoever has to fix it.
    return iso;
  }
}

/** `"12 Sep 2026"` — an admission date, a fee month, an exam day. */
export function formatDhakaDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: DHAKA_TZ,
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/** `"02:30 pm"` — a period's start and end on the teacher's board. */
export function formatDhakaTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: DHAKA_TZ,
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/**
 * Today in Dhaka, as `YYYY-MM-DD`.
 *
 * `toISOString().slice(0, 10)` would be a day behind for the first six hours
 * of every Bangladeshi morning, which is exactly when attendance is taken.
 */
export function todayInDhaka(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: DHAKA_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}

/** A date offset from today (`-1` yesterday, `-7` last week) as `YYYY-MM-DD`. */
export function dateOffsetInDhaka(dayOffset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: DHAKA_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d);
}

/** The current year and month in Dhaka — what a fee month or an attendance
 *  register defaults to. `month` is 1-based, matching the API. */
export function currentMonthInDhaka(): { year: number; month: number } {
  const [year, month] = todayInDhaka().split('-').map(Number);
  return { year, month };
}
