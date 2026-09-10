import type { AttendanceStatus, RegisterDay, RegisterStudent } from '../../lib/api';

/**
 * What the attendance screens agree on: the statuses, their one-letter keys,
 * their colours, and the percentage rule.
 *
 * The percentage in particular is here and not in a component because the
 * server computes the same number (`attendance/services.py::_totals`) and the
 * grid recomputes it live as cells change (`docs/02` §4.4). Two implementations
 * that disagree by a rounding rule is a teacher watching a figure change when
 * they press Save.
 */

export interface StatusDef {
  value: AttendanceStatus;
  /** The keyboard key, and the letter drawn in the cell. */
  key: string;
  /** English source string for `t()`. */
  label: string;
  /** Cell colours. Written out in full — Tailwind only ships classes it can
   *  see in the source, so a class built from a variable never arrives. */
  cell: string;
  dot: string;
}

/**
 * The four the keyboard reaches, in the order `docs/02` §4.4 names them:
 * `P` / `A` / `L` / `H`. Late and half-day are reachable by clicking through
 * the cycle — they are real statuses the server accepts, but they are not what
 * a teacher is typing sixty times.
 */
export const STATUSES: StatusDef[] = [
  { value: 'present', key: 'P', label: 'Present', cell: 'bg-green-50 text-green-700', dot: 'bg-green-500' },
  { value: 'absent', key: 'A', label: 'Absent', cell: 'bg-red-50 text-red-700', dot: 'bg-red-500' },
  { value: 'late', key: 'T', label: 'Late', cell: 'bg-amber-50 text-amber-700', dot: 'bg-amber-500' },
  { value: 'leave', key: 'L', label: 'Leave', cell: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
  { value: 'half_day', key: 'F', label: 'Half day', cell: 'bg-purple-50 text-purple-700', dot: 'bg-purple-500' },
  { value: 'holiday', key: 'H', label: 'Holiday', cell: 'bg-gray-100 text-gray-500', dot: 'bg-gray-400' },
];

export const STATUS_BY_VALUE: Record<AttendanceStatus, StatusDef> = Object.fromEntries(
  STATUSES.map((s) => [s.value, s]),
) as Record<AttendanceStatus, StatusDef>;

/** Keyboard letter → status. `P A L H` are `docs/02` §4.4's own four. */
export const KEY_TO_STATUS: Record<string, AttendanceStatus> = {
  P: 'present',
  A: 'absent',
  L: 'leave',
  H: 'holiday',
  T: 'late',
  F: 'half_day',
};

/** Clicking a cell walks present → absent → leave → cleared. The three a
 *  teacher actually uses, and clearing back to unmarked, which is the only way
 *  to undo a mis-tap with a thumb. */
export function cycleStatus(current: AttendanceStatus | null): AttendanceStatus | null {
  if (current === null) return 'present';
  if (current === 'present') return 'absent';
  if (current === 'absent') return 'leave';
  return null;
}

/** `2026-03` → `2026-04`, and `2026-12` → `2027-01`. */
export function shiftMonth(month: string, delta: number): string {
  const [year, m] = month.split('-').map(Number);
  const zeroBased = m - 1 + delta;
  const y = year + Math.floor(zeroBased / 12);
  const mm = ((zeroBased % 12) + 12) % 12;
  return `${y}-${String(mm + 1).padStart(2, '0')}`;
}

/** `2026-03-09` → `9`. The day number in the column header, nothing else. */
export function dayNumber(iso: string): string {
  return String(Number(iso.slice(8, 10)));
}

/** `2026-03-09` → `Mon`. Drawn under the day number so a teacher can see the
 *  week without counting columns. */
export function weekdayShort(iso: string): string {
  const names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  return names[new Date(`${iso}T00:00:00`).getDay()];
}

/**
 * The attendance percentage, exactly as the server computes it.
 *
 * `late` counts as present because the student was there; `half_day` counts as
 * half; `holiday` is excluded from the denominator, so a percentage never drops
 * because the month is not finished.
 */
export function percentOf(statuses: (AttendanceStatus | null)[]): number | null {
  let marked = 0;
  let attended = 0;
  for (const status of statuses) {
    if (status === null || status === 'holiday') continue;
    marked += 1;
    if (status === 'present' || status === 'late') attended += 1;
    else if (status === 'half_day') attended += 0.5;
  }
  return marked === 0 ? null : Math.round((1000 * attended) / marked) / 10;
}

/** The key a dirty cell is held under. One string, so the map cannot be
 *  keyed on a student in one place and a roll number in another. */
export function cellKey(student: number, date: string): string {
  return `${student}|${date}`;
}

/**
 * The status showing in a cell right now: the unsaved edit if there is one,
 * otherwise what the server sent, otherwise nothing.
 */
export function effectiveStatus(
  student: RegisterStudent,
  date: string,
  draft: Map<string, AttendanceStatus>,
): AttendanceStatus | null {
  const edited = draft.get(cellKey(student.student, date));
  if (edited) return edited;
  return student.cells[date]?.status ?? null;
}

/** A student's display name, Bangla first — this is a Bangla-default product
 *  and the register is read at a glance. */
export function studentName(row: { name: string; name_bn: string }): string {
  return row.name_bn || row.name;
}

/** The days a teacher may actually type into. Off days and future dates are
 *  the server's decision, carried on each day (`docs/02` §5.1). */
export function markableDays(days: RegisterDay[]): RegisterDay[] {
  return days.filter((d) => d.is_markable);
}
