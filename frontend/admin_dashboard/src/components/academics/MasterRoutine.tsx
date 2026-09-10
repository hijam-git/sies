import { useMemo } from 'react';
import type { AcademicClass, ClassRoutine, DayOfWeek, Period, Teacher } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { WEEK_DAYS, classLabel, periodLabel, shortTime } from './shared';

/**
 * One day of the whole institution — every class, or every teacher, at once.
 *
 * The per-class grid answers "what does Class 5 do this week". It cannot answer
 * the two questions an office actually asks at 8am: *is anybody free third
 * period*, and *is any teacher double-booked*. Both are read off the same rows
 * already loaded for the clash check, turned ninety degrees: one row per class
 * or per teacher, one column per period.
 *
 * Read-only by design. Editing happens in the class's own grid, and a cell here
 * is a link into it — a second editable surface for the same table is a second
 * place for the clash rule to be got wrong.
 *
 * **Teacher rows include teachers with an empty day**, which is the point: a
 * blank row is the free teacher somebody is looking for. A class with no
 * routine at all is dropped instead, because that is a class nobody has built
 * yet rather than a fact about today.
 */

type Mode = 'classes' | 'teachers';

export default function MasterRoutine({
  mode,
  day,
  onDayChange,
  routines,
  periods,
  classes,
  teachers,
  onOpenClass,
}: {
  mode: Mode;
  day: DayOfWeek;
  onDayChange: (day: DayOfWeek) => void;
  routines: ClassRoutine[];
  /** Teaching periods only — a break column would be empty in every row. */
  periods: Period[];
  classes: AcademicClass[];
  teachers: Teacher[];
  onOpenClass: (classId: number) => void;
}) {
  const { t } = useT();

  const today = useMemo(() => routines.filter((r) => r.day_of_week === day), [routines, day]);

  /** `${rowKey}:${periodId}` → the lessons in that slot. A list, not one row:
   *  two lessons for one teacher in one period is exactly the double-booking
   *  this view exists to show, so it is drawn rather than hidden by a Map that
   *  keeps the last write. */
  const slots = useMemo(() => {
    const map = new Map<string, ClassRoutine[]>();
    for (const row of today) {
      const key = `${mode === 'classes' ? row.academic_class : row.teacher}:${row.period}`;
      const list = map.get(key);
      if (list) list.push(row);
      else map.set(key, [row]);
    }
    return map;
  }, [today, mode]);

  const rows = useMemo(() => {
    if (mode === 'teachers') {
      return teachers.map((x) => ({ id: x.id, label: x.name_bn || x.name, sub: x.teacher_id }));
    }
    // Only classes that have a routine — the rest are unbuilt, not idle.
    const withRows = new Set(routines.map((r) => r.academic_class));
    return classes
      .filter((c) => withRows.has(c.id))
      .map((c) => ({ id: c.id, label: classLabel(c), sub: String(c.year) }));
  }, [mode, teachers, classes, routines]);

  return (
    <div className="space-y-3">
      {/* The day strip scrolls inside itself; the page never scrolls sideways. */}
      <div className="scroll-x -mx-1 px-1">
        <div className="flex w-max gap-1">
          {WEEK_DAYS.map((d) => (
            <button
              key={d.value}
              type="button"
              onClick={() => onDayChange(d.value)}
              aria-pressed={day === d.value}
              className={`min-h-[40px] whitespace-nowrap rounded-lg px-3 text-sm font-medium ${
                day === d.value
                  ? 'bg-blue-600 text-white'
                  : 'border border-gray-200 bg-white text-gray-600'
              }`}
            >
              {t(d.label)}
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 || periods.length === 0 ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Nothing is scheduled yet.')}
        </div>
      ) : (
        <div className="scroll-x rounded-xl border border-gray-100 bg-white shadow-sm">
          <table className="w-max min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left">
                {/* Sticky, because the name is what a scrolled-right column is
                    meaningless without. */}
                <th className="sticky left-0 z-10 bg-gray-50 px-3 py-2 font-semibold text-gray-600">
                  {t(mode === 'classes' ? 'Class' : 'Teacher')}
                </th>
                {periods.map((p) => (
                  <th key={p.id} className="px-3 py-2 font-semibold text-gray-600">
                    <span className="block whitespace-nowrap">{periodLabel(p)}</span>
                    <span className="block whitespace-nowrap text-xs font-normal text-gray-400">
                      {shortTime(p.start_time)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.map((r) => (
                <tr key={r.id} className="align-top">
                  <th
                    scope="row"
                    className="sticky left-0 z-10 bg-white px-3 py-2 text-left font-medium text-gray-900"
                  >
                    <span className="block whitespace-nowrap">{r.label}</span>
                    {r.sub && (
                      <span className="block whitespace-nowrap font-mono text-xs font-normal text-gray-400">
                        {r.sub}
                      </span>
                    )}
                  </th>
                  {periods.map((p) => {
                    const lessons = slots.get(`${r.id}:${p.id}`) ?? [];
                    if (lessons.length === 0) {
                      return (
                        <td key={p.id} className="px-3 py-2 text-xs text-gray-300">
                          {mode === 'teachers' ? t('Free') : '—'}
                        </td>
                      );
                    }
                    // Two lessons in one slot is a clash on the teacher view and
                    // a section split on the class view. Both are shown; the
                    // clash is coloured because only one of them is a mistake.
                    const clash = mode === 'teachers' && lessons.length > 1;
                    return (
                      <td key={p.id} className={`px-3 py-2 ${clash ? 'bg-red-50' : ''}`}>
                        {lessons.map((lesson) => (
                          <button
                            key={lesson.id}
                            type="button"
                            onClick={() => onOpenClass(lesson.academic_class)}
                            className="block w-full whitespace-nowrap text-left hover:underline"
                          >
                            <span className="block font-medium text-gray-900">
                              {mode === 'teachers'
                                ? classLabel(classes.find((c) => c.id === lesson.academic_class))
                                : lesson.subject_name}
                            </span>
                            <span className="block text-xs text-gray-600">
                              {mode === 'teachers' ? lesson.subject_name : lesson.teacher_name}
                            </span>
                          </button>
                        ))}
                        {clash && (
                          <span className="mt-1 block text-xs font-medium text-red-700">
                            {t('Double-booked')}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
