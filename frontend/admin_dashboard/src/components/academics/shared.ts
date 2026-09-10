import type { AcademicClass, Period, Session, Stream, Teacher } from '../../lib/api';

/**
 * What the four academics tabs all need, fetched once by the page.
 *
 * Sessions, streams, classes and teachers are read by every tab: the routine
 * grid picks a class, the subject form picks a stream, the class form picks a
 * class teacher. Four tabs fetching the same four lists on every switch is
 * sixteen requests for data that changes once a year.
 */
export interface AcademicsData {
  sessions: Session[];
  streams: Stream[];
  teachers: Teacher[];
  classes: AcademicClass[];
  /** Re-reads the classes after a tab has changed one, so the routine's class
   *  picker does not go stale behind the Classes tab. */
  reloadClasses: () => Promise<void>;
}

/**
 * The Bangladeshi week, in the order it is printed: Saturday first, Friday the
 * weekend. `day_of_week` on the API is this index, NOT `Date.getDay()` — the
 * two agree on nothing but Wednesday.
 */
export const WEEK_DAYS: { value: 0 | 1 | 2 | 3 | 4 | 5 | 6; label: string }[] = [
  { value: 0, label: 'Saturday' },
  { value: 1, label: 'Sunday' },
  { value: 2, label: 'Monday' },
  { value: 3, label: 'Tuesday' },
  { value: 4, label: 'Wednesday' },
  { value: 5, label: 'Thursday' },
  { value: 6, label: 'Friday' },
];

/** Today's index in the week above, for defaulting the phone day picker to the
 *  day the user is actually standing in. */
export function todayWeekIndex(): 0 | 1 | 2 | 3 | 4 | 5 | 6 {
  // `getDay()` is Sunday=0; the routine is Saturday=0, so Saturday's 6 maps to
  // 0 and everything else shifts up by one.
  const sundayFirst = new Date().getDay();
  return ((sundayFirst + 1) % 7) as 0 | 1 | 2 | 3 | 4 | 5 | 6;
}

/** `"09:00:00"` → `"09:00"`. The API sends seconds; `<input type="time">`
 *  silently refuses a value it did not expect and shows an empty box. */
export function timeInputValue(value: string | null | undefined): string {
  return value ? value.slice(0, 5) : '';
}

/** `"09:00:00"` → `"9:00"`, for a cell that has a column and not a paragraph. */
export function shortTime(value: string | null | undefined): string {
  if (!value) return '';
  const [h, m] = value.split(':');
  return `${Number(h)}:${m}`;
}

/** A period's own label, or its clock time when it has no name worth showing. */
export function periodLabel(period: Period | undefined): string {
  if (!period) return '';
  return period.name_bn || period.name || `${shortTime(period.start_time)}`;
}

export function classLabel(row: AcademicClass | undefined): string {
  if (!row) return '';
  return row.name_bn || row.name;
}
