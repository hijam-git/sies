import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { apiClient } from '../../lib/api';
import type {
  AcademicClass,
  AttendanceStatus,
  MonthRegister,
  RegisterCellInput,
  RegisterDay,
  RegisterStudent,
  Section,
  SkippedCell,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, selectCls } from '../common/styles';
import { currentMonthInDhaka, todayInDhaka } from '../../lib/timezone';
import {
  KEY_TO_STATUS,
  STATUSES,
  STATUS_BY_VALUE,
  cellKey,
  cycleStatus,
  dayNumber,
  effectiveStatus,
  percentOf,
  shiftMonth,
  studentName,
  weekdayShort,
} from './shared';

/**
 * The month register — `docs/02` §4.4, the screen teachers spend their hours in.
 *
 * Three things about it are not decoration:
 *
 * **Batch save.** Sixty students by thirty days is 1,800 cells. Only the dirty
 * ones are held (`draft`), and they go in ONE POST to `register/bulk/`. A
 * per-cell save would be 1,800 requests, and the endpoint exists precisely so
 * that it is not.
 *
 * **Keyboard first.** Arrows move, `P`/`A`/`L`/`H` set and advance, Enter drops
 * to the next student on the same day. A teacher marking sixty students should
 * never touch the mouse, and the two bulk actions — a whole day, a whole
 * student — are how attendance actually goes: mark everyone present, then
 * correct the three who are not.
 *
 * **Two layouts, not one that shrinks.** From `md` up it is the grid: students
 * down, days across, first column frozen. Below `md` it defaults to ONE DAY as
 * a vertical list with prev/next arrows (`CLAUDE.md` §7a), because that is what
 * a teacher standing in front of a class wants on a phone; the full grid stays
 * available behind a toggle for anyone who would rather pinch and scroll.
 *
 * What is *not* decided here: whether a cell may be marked at all. Every day
 * carries the server's own `is_markable` and reason, and the bulk endpoint
 * re-decides it inside the transaction — a cell it refuses comes back in
 * `skipped` and is shown as it came, naming the student and the reason, because
 * "some cells were not saved" is not something anybody can act on.
 */

interface Props {
  classes: AcademicClass[];
  /** Fetched once by the page — every tab needs it. */
  sections: Section[];
  onSectionsNeeded: (classId: string) => void;
}

type PhoneView = 'day' | 'grid';

export default function MonthRegisterTab({ classes, sections, onSectionsNeeded }: Props) {
  const { t, lang } = useT();
  const { can } = usePermissions();

  const [classChoice, setClassChoice] = useState('');
  const [sectionId, setSectionId] = useState('');
  const [month, setMonth] = useState(() => {
    const { year, month: m } = currentMonthInDhaka();
    return `${year}-${String(m).padStart(2, '0')}`;
  });

  const [register, setRegister] = useState<MonthRegister | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  /** Dirty cells only — the whole point of the batch endpoint. */
  const [draft, setDraft] = useState<Map<string, AttendanceStatus>>(new Map());
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);
  const [skipped, setSkipped] = useState<SkippedCell[]>([]);

  const [phoneView, setPhoneView] = useState<PhoneView>('day');
  const [dayIndex, setDayIndex] = useState(0);
  /** Which cell the keyboard is on, as [student row, day column]. */
  const [focus, setFocus] = useState<[number, number] | null>(null);
  const cellRefs = useRef(new Map<string, HTMLButtonElement>());

  const mayEdit = can('attendance', 'take') || can('attendance', 'update');

  const classId = classes.some((c) => String(c.id) === classChoice)
    ? classChoice
    : String(classes[0]?.id ?? '');

  const classSections = useMemo(
    () => sections.filter((s) => String(s.academic_class) === classId),
    [sections, classId],
  );

  useEffect(() => {
    if (classId) onSectionsNeeded(classId);
  }, [classId, onSectionsNeeded]);

  const load = useCallback(async () => {
    if (!classId) {
      setRegister(null);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const data = await apiClient.getMonthRegister({
        academicClass: Number(classId),
        section: sectionId ? Number(sectionId) : null,
        month,
      });
      setRegister(data);
      setDraft(new Map());
      setSkipped([]);
      setSavedCount(null);
      // Land on today when the month contains it, so the phone view opens on
      // the day the teacher is standing in rather than on the 1st.
      const today = todayInDhaka();
      const todayIndex = data.days.findIndex((d) => d.date === today);
      setDayIndex(todayIndex >= 0 ? todayIndex : Math.max(0, data.days.length - 1));
    } catch (err) {
      setRegister(null);
      setLoadError(apiErrorText(err, t, t('Could not load the register.')));
    } finally {
      setLoading(false);
    }
  }, [classId, sectionId, month, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  // ── Editing ─────────────────────────────────────────────────────────────

  const setCell = useCallback(
    (student: RegisterStudent, day: RegisterDay, status: AttendanceStatus | null) => {
      if (!mayEdit || !day.is_markable) return;
      setDraft((prev) => {
        const next = new Map(prev);
        const key = cellKey(student.student, day.date);
        const saved = student.cells[day.date]?.status ?? null;
        if (status === null) {
          // Clearing a cell that was never saved just drops the edit; there is
          // no "unmark" on the API, so a saved cell cannot be cleared at all.
          next.delete(key);
        } else if (status === saved) {
          next.delete(key);
        } else {
          next.set(key, status);
        }
        return next;
      });
    },
    [mayEdit],
  );

  const markWholeDay = (day: RegisterDay, status: AttendanceStatus) => {
    if (!register || !mayEdit || !day.is_markable) return;
    setDraft((prev) => {
      const next = new Map(prev);
      for (const student of register.students) {
        const key = cellKey(student.student, day.date);
        if ((student.cells[day.date]?.status ?? null) === status) next.delete(key);
        else next.set(key, status);
      }
      return next;
    });
  };

  const markWholeStudent = (student: RegisterStudent, status: AttendanceStatus) => {
    if (!register || !mayEdit) return;
    setDraft((prev) => {
      const next = new Map(prev);
      for (const day of register.days) {
        if (!day.is_markable) continue;
        const key = cellKey(student.student, day.date);
        if ((student.cells[day.date]?.status ?? null) === status) next.delete(key);
        else next.set(key, status);
      }
      return next;
    });
  };

  // ── Keyboard ────────────────────────────────────────────────────────────

  // Moving is a state change and the DOM focus follows it in an effect, rather
  // than the handler reaching into the ref map itself: a keydown handler that
  // reads refs is a handler React can hand a stale element to, and the two
  // would then disagree about which cell is current.
  const focusCell = useCallback((si: number, di: number) => setFocus([si, di]), []);

  useEffect(() => {
    if (focus === null) return;
    cellRefs.current.get(`${focus[0]}:${focus[1]}`)?.focus();
  }, [focus]);

  const onCellKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    si: number,
    di: number,
  ) => {
    if (!register) return;
    const lastStudent = register.students.length - 1;
    const lastDay = register.days.length - 1;
    const key = event.key.length === 1 ? event.key.toUpperCase() : event.key;

    if (key === 'ArrowRight') {
      event.preventDefault();
      focusCell(si, Math.min(lastDay, di + 1));
      return;
    }
    if (key === 'ArrowLeft') {
      event.preventDefault();
      focusCell(si, Math.max(0, di - 1));
      return;
    }
    if (key === 'ArrowDown') {
      event.preventDefault();
      focusCell(Math.min(lastStudent, si + 1), di);
      return;
    }
    if (key === 'ArrowUp') {
      event.preventDefault();
      focusCell(Math.max(0, si - 1), di);
      return;
    }
    if (key === 'Enter') {
      // Down a student, same day — the register is read student by student when
      // a name is called out, and column by column when a day is corrected.
      event.preventDefault();
      focusCell(Math.min(lastStudent, si + 1), di);
      return;
    }
    if (key === 'Backspace' || key === 'Delete') {
      event.preventDefault();
      setCell(register.students[si], register.days[di], null);
      return;
    }

    const status = KEY_TO_STATUS[key];
    if (status) {
      event.preventDefault();
      setCell(register.students[si], register.days[di], status);
      // Advance to the next markable day, skipping the Fridays: stopping on a
      // column that refuses input is a keystroke wasted on every weekend.
      let next = di + 1;
      while (next <= lastDay && !register.days[next].is_markable) next += 1;
      if (next <= lastDay) focusCell(si, next);
    }
  };

  // ── Saving ──────────────────────────────────────────────────────────────

  const save = async () => {
    if (!register || draft.size === 0) return;
    setSaving(true);
    setSaveError(null);
    setSkipped([]);
    const cells: RegisterCellInput[] = [...draft.entries()].map(([key, status]) => {
      const [student, date] = key.split('|');
      return { student: Number(student), date, status };
    });
    try {
      const result = await apiClient.saveMonthRegister({
        academicClass: register.class,
        section: register.section,
        month: register.month,
        cells,
      });
      setSavedCount(result.saved);
      setSkipped(result.skipped);
      // Re-read rather than patching state: `taken_by`, `taken_at` and the
      // server's own totals all changed, and a grid that shows a stale taker is
      // a grid that answers "who marked my son absent" wrongly.
      await load();
      setSavedCount(result.saved);
      setSkipped(result.skipped);
    } catch (err) {
      setSaveError(apiErrorText(err, t, t('Could not save the register.')));
    } finally {
      setSaving(false);
    }
  };

  // ── Derived ─────────────────────────────────────────────────────────────

  /** Per-student percentage and per-day present count, recomputed as cells
   *  change — `docs/02` §4.4's live totals. */
  const totals = useMemo(() => {
    if (!register) return { perStudent: new Map<number, number | null>(), perDay: new Map<string, number>() };
    const perStudent = new Map<number, number | null>();
    const perDay = new Map<string, number>();
    for (const day of register.days) perDay.set(day.date, 0);

    for (const student of register.students) {
      const statuses: (AttendanceStatus | null)[] = [];
      for (const day of register.days) {
        const status = effectiveStatus(student, day.date, draft);
        statuses.push(status);
        if (status === 'present' || status === 'late') {
          perDay.set(day.date, (perDay.get(day.date) ?? 0) + 1);
        }
      }
      perStudent.set(student.student, percentOf(statuses));
    }
    return { perStudent, perDay };
  }, [register, draft]);

  const days = register?.days ?? [];
  const day = days[Math.min(dayIndex, Math.max(0, days.length - 1))];
  const chosenClass = classes.find((c) => String(c.id) === classId);

  // ── Pieces shared by both layouts ───────────────────────────────────────

  const statusLetter = (status: AttendanceStatus | null) =>
    status ? STATUS_BY_VALUE[status].key : '';

  const cellClasses = (
    status: AttendanceStatus | null,
    markable: boolean,
    dirty: boolean,
  ) => {
    if (!markable) return 'bg-gray-100 text-gray-300';
    const base = status ? STATUS_BY_VALUE[status].cell : 'bg-white text-gray-300';
    return `${base} ${dirty ? 'ring-2 ring-inset ring-blue-400' : ''}`;
  };

  const dayReason = (d: RegisterDay) => (lang === 'bn' ? d.reason_text_bn : d.reason_text);

  const renderGrid = (keyboard: boolean) => register && (
    // The one container allowed to scroll sideways — the body never does
    // (`CLAUDE.md` §7a rule 1).
    <div className="scroll-x rounded-xl border border-gray-100 bg-white shadow-sm">
      <table className="border-collapse">
        <thead>
          <tr>
            <th className="sticky left-0 z-20 min-w-[9rem] border-b border-r border-gray-200 bg-white px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              {t('Student')}
            </th>
            {days.map((d) => (
              <th
                key={d.date}
                title={d.is_markable ? undefined : dayReason(d)}
                className={`border-b border-gray-100 px-0 py-1 text-center text-xs font-medium ${
                  d.is_markable ? 'text-gray-600' : 'bg-gray-100 text-gray-400'
                }`}
              >
                <span className="block">{dayNumber(d.date)}</span>
                <span className="block text-[10px] font-normal text-gray-400">
                  {t(weekdayShort(d.date))}
                </span>
                {/* The column bulk action, right where the column is —
                    "mark whole day present", then correct the few who are not. */}
                <button
                  type="button"
                  disabled={!mayEdit || !d.is_markable}
                  onClick={() => markWholeDay(d, 'present')}
                  title={t('Mark whole day present')}
                  aria-label={`${t('Mark whole day present')} — ${d.date}`}
                  className="mt-0.5 block w-full py-1 text-[11px] text-green-700 hover:bg-green-50 disabled:invisible"
                >
                  ✓
                </button>
              </th>
            ))}
            <th className="border-b border-l border-gray-200 px-2 py-2 text-center text-xs font-medium uppercase tracking-wide text-gray-500">
              %
            </th>
          </tr>
        </thead>
        <tbody>
          {register.students.map((student, si) => (
            <tr key={student.student} className="border-b border-gray-100 last:border-0">
              {/* Frozen first column: the student stays readable while thirty
                  day columns scroll under the thumb (`CLAUDE.md` §7a). */}
              <th className="sticky left-0 z-10 min-w-[9rem] border-r border-gray-200 bg-white px-3 py-1 text-left">
                <span className="block truncate text-sm font-medium text-gray-900">
                  {studentName(student)}
                </span>
                <span className="flex items-center gap-2 text-[11px] text-gray-400">
                  <span>{student.roll ?? student.student_code}</span>
                  <button
                    type="button"
                    disabled={!mayEdit}
                    onClick={() => markWholeStudent(student, 'present')}
                    className="text-green-700 hover:underline disabled:hidden"
                  >
                    {t('All present')}
                  </button>
                  <button
                    type="button"
                    disabled={!mayEdit}
                    onClick={() => markWholeStudent(student, 'absent')}
                    className="text-red-700 hover:underline disabled:hidden"
                  >
                    {t('All absent')}
                  </button>
                </span>
              </th>
              {days.map((d, di) => {
                const status = effectiveStatus(student, d.date, draft);
                const dirty = draft.has(cellKey(student.student, d.date));
                return (
                  <td key={d.date} className="p-0">
                    <button
                      type="button"
                      ref={(el) => {
                        if (!keyboard) return;
                        if (el) cellRefs.current.set(`${si}:${di}`, el);
                        else cellRefs.current.delete(`${si}:${di}`);
                      }}
                      disabled={!mayEdit || !d.is_markable}
                      onClick={() => setCell(student, d, cycleStatus(status))}
                      onFocus={() => setFocus([si, di])}
                      onKeyDown={(e) => onCellKeyDown(e, si, di)}
                      tabIndex={focus === null ? (si === 0 && di === 0 ? 0 : -1) : focus[0] === si && focus[1] === di ? 0 : -1}
                      aria-label={`${studentName(student)} ${d.date} ${status ? t(STATUS_BY_VALUE[status].label) : t('Not marked')}`}
                      className={`h-11 w-9 border border-gray-100 text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-600 disabled:cursor-not-allowed ${cellClasses(status, d.is_markable, dirty)}`}
                    >
                      {statusLetter(status)}
                    </button>
                  </td>
                );
              })}
              <td className="border-l border-gray-200 px-2 text-center text-sm font-medium text-gray-700">
                {totals.perStudent.get(student.student) === null
                  ? '—'
                  : `${totals.perStudent.get(student.student)}%`}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-gray-50">
            <th className="sticky left-0 z-10 border-r border-t border-gray-200 bg-gray-50 px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              {t('Present')}
            </th>
            {days.map((d) => (
              <td
                key={d.date}
                className="border-t border-gray-200 text-center text-xs font-medium text-gray-600"
              >
                {d.is_markable ? (totals.perDay.get(d.date) ?? 0) : ''}
              </td>
            ))}
            <td className="border-l border-t border-gray-200" />
          </tr>
        </tfoot>
      </table>
    </div>
  );

  const singleDay = register && day && (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 rounded-xl border border-gray-100 bg-white p-2 shadow-sm">
        <button
          type="button"
          onClick={() => setDayIndex(Math.max(0, dayIndex - 1))}
          disabled={dayIndex === 0}
          className={btnSecondary}
          aria-label={t('Previous day')}
        >
          ‹
        </button>
        <div className="text-center">
          <span className="block text-sm font-semibold text-gray-900">
            {dayNumber(day.date)} · {t(weekdayShort(day.date))}
          </span>
          <span className="block text-xs text-gray-500">
            {day.is_markable
              ? `${t('Present')}: ${totals.perDay.get(day.date) ?? 0} / ${register.students.length}`
              : dayReason(day)}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setDayIndex(Math.min(days.length - 1, dayIndex + 1))}
          disabled={dayIndex >= days.length - 1}
          className={btnSecondary}
          aria-label={t('Next day')}
        >
          ›
        </button>
      </div>

      <button
        type="button"
        disabled={!mayEdit || !day.is_markable}
        onClick={() => markWholeDay(day, 'present')}
        className={`${btnPrimary} w-full justify-center`}
      >
        {t('Mark whole day present')}
      </button>

      <ul className="divide-y divide-gray-100 rounded-xl border border-gray-100 bg-white shadow-sm">
        {register.students.map((student) => {
          const status = effectiveStatus(student, day.date, draft);
          const dirty = draft.has(cellKey(student.student, day.date));
          return (
            <li key={student.student} className="px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-gray-900">
                    {studentName(student)}
                  </span>
                  <span className="block text-xs text-gray-400">
                    {student.roll ?? student.student_code}
                    {' · '}
                    {totals.perStudent.get(student.student) === null
                      ? '—'
                      : `${totals.perStudent.get(student.student)}%`}
                  </span>
                </span>
                <span className="flex shrink-0 gap-1">
                  {STATUSES.slice(0, 4).map((s) => (
                    <button
                      key={s.value}
                      type="button"
                      disabled={!mayEdit || !day.is_markable}
                      onClick={() => setCell(student, day, s.value)}
                      aria-pressed={status === s.value}
                      aria-label={t(s.label)}
                      className={`h-11 w-11 rounded-lg border text-sm font-semibold disabled:opacity-40 ${
                        status === s.value
                          ? `${s.cell} border-transparent ${dirty ? 'ring-2 ring-blue-400' : ''}`
                          : 'border-gray-200 bg-white text-gray-400'
                      }`}
                    >
                      {s.key}
                    </button>
                  ))}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Class')}</span>
          <select
            value={classId}
            onChange={(e) => {
              setClassChoice(e.target.value);
              setSectionId('');
            }}
            className={selectCls}
          >
            {classes.length === 0 && <option value="">{t('No classes are assigned to you.')}</option>}
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name_bn || c.name}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Section')}</span>
          <select
            value={sectionId}
            onChange={(e) => setSectionId(e.target.value)}
            className={selectCls}
          >
            <option value="">{t('Whole class')}</option>
            {classSections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name_bn || s.name}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Month')}</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setMonth(shiftMonth(month, -1))}
              className={btnSecondary}
              aria-label={t('Previous month')}
            >
              ‹
            </button>
            <input
              type="month"
              value={month}
              onChange={(e) => e.target.value && setMonth(e.target.value)}
              className="min-h-[44px] w-full rounded-lg border border-gray-200 bg-white px-3 text-base text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="button"
              onClick={() => setMonth(shiftMonth(month, 1))}
              className={btnSecondary}
              aria-label={t('Next month')}
            >
              ›
            </button>
          </div>
        </label>
      </div>

      {loadError && <FormError message={loadError} />}
      {saveError && <FormError message={saveError} />}

      {savedCount !== null && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {`${t('Saved')}: ${savedCount}`}
        </div>
      )}

      {/* The server refused these, and it says why per cell. Shown in full
          rather than counted — a teacher can only act on a named student. */}
      {skipped.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-medium">{`${t('Not saved')}: ${skipped.length}`}</p>
          <ul className="mt-1 space-y-0.5">
            {skipped.map((row) => {
              const who = register?.students.find((s) => s.student === row.student);
              return (
                <li key={`${row.student}|${row.date}`}>
                  {`${who ? studentName(who) : row.student} · ${row.date} — ${
                    lang === 'bn' ? row.reason_text_bn : row.reason_text
                  }`}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {!mayEdit && (
        <p className="text-sm text-gray-500">
          {t('You can read this register but not change it.')}
        </p>
      )}

      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {!loading && register && register.students.length === 0 && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('No students are enrolled in this class.')}
        </div>
      )}

      {register && register.students.length > 0 && (
        <>
          {/* ── Phone: one day by default, the grid behind a toggle ──────── */}
          <div className="md:hidden">
            <div className="mb-3 flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium text-gray-700">
                {chosenClass ? chosenClass.name_bn || chosenClass.name : ''}
              </span>
              <button
                type="button"
                onClick={() => setPhoneView(phoneView === 'day' ? 'grid' : 'day')}
                className={btnSecondary}
              >
                {phoneView === 'day' ? t('Grid view') : t('Single day')}
              </button>
            </div>
            {phoneView === 'day' ? singleDay : renderGrid(false)}
          </div>

          {/* ── md and up: the register itself ───────────────────────────── */}
          <div className="hidden md:block">{renderGrid(true)}</div>

          <p className="hidden text-xs text-gray-500 md:block">
            {t('Arrow keys move · P present · A absent · L leave · H holiday · Enter next student')}
          </p>
        </>
      )}

      {/* The action bar sticks to the bottom so Save is reachable with a thumb
          after thirty rows of scrolling, and clears the phone's home indicator
          (`CLAUDE.md` §7a rule 9). */}
      {register && draft.size > 0 && (
        <div className="sticky bottom-0 z-30 -mx-4 border-t border-gray-200 bg-white/95 px-4 pb-[env(safe-area-inset-bottom)] pt-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
          <div className="flex items-center justify-between gap-3 pb-3">
            <span className="text-sm text-gray-600">
              {`${draft.size} ${t('unsaved cells')}`}
            </span>
            <span className="flex gap-2">
              <button type="button" onClick={() => setDraft(new Map())} className={btnSecondary}>
                {t('Discard')}
              </button>
              <button type="button" onClick={() => void save()} disabled={saving} className={btnPrimary}>
                {saving ? t('Saving…') : t('Save')}
              </button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
