import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/api';
import type { ClassRoutine, DayOfWeek, Period } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { apiErrorText } from '../lib/apiErrors';
import { FormError } from '../components/common/Field';
import NavIcon from '../components/common/NavIcon';
import StatCard from '../components/common/StatCard';
import { btnSecondary } from '../components/common/styles';
import { WEEK_DAYS, periodLabel, shortTime, todayWeekIndex } from '../components/academics/shared';
import { nowTimeInDhaka } from '../lib/timezone';

/**
 * My routine — a teacher's own week (`docs/08` D7).
 *
 * The today board answers "what is left today". This answers the question a
 * teacher actually holds in their head: **when do I teach, and what.** Same
 * data, same card idiom, one week wider.
 *
 * **Two layouts, not one that shrinks** — the answer `RoutineTab` already found
 * for the admin's grid, and there is no reason for a second one. From `md` up it
 * is the printed week: periods down a sticky left column, Saturday to Friday
 * across. Below `md` it is a day picker and that day's periods as a vertical
 * list, because seven columns of subject-plus-class at 360px is unreadable at
 * any zoom (`CLAUDE.md` §7a).
 *
 * **Empty periods are drawn, not skipped.** A teacher reading a timetable is
 * looking for their free hours as hard as their busy ones, and a grid that omits
 * them cannot be counted down. Breaks come from `Period.is_break` and get a band
 * of their own for the same reason: drop them and the day reads as if it has no
 * gaps in it.
 *
 * The rows come from `/class-routines/my-routine/`, which is filtered to the
 * caller's own `Teacher` row server-side. There is no teacher id on this screen
 * for anybody to change.
 */

/** How often the "now" marker re-reads the clock. A period boundary is a minute
 *  wide and this screen stays open across one. */
const CLOCK_TICK_MS = 30_000;

export default function MyRoutinePage() {
  const { t, lang } = useT();
  const { user } = useAuth();

  const [rows, setRows] = useState<ClassRoutine[]>([]);
  const [sessionName, setSessionName] = useState('');
  const [periods, setPeriods] = useState<Period[]>([]);
  const [day, setDay] = useState<DayOfWeek>(todayWeekIndex());
  const [now, setNow] = useState(nowTimeInDhaka());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const today = todayWeekIndex();
  const dayStrip = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The bell schedule is a second read because it is institution-wide and
      // carries the rows the teacher has no lesson in — which are exactly the
      // free periods this screen exists to show.
      const [mine, bells] = await Promise.all([
        apiClient.getMyRoutine(),
        apiClient.listAll<Period>('/periods/', '?is_active=true&ordering=order'),
      ]);
      setRows(mine.rows);
      setSessionName(mine.session_name);
      setPeriods(bells);
    } catch (err) {
      setRows([]);
      setPeriods([]);
      setError(apiErrorText(err, t, t('Could not load your routine.')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Deferred by a tick, like the other list screens: `load` sets state
  // synchronously, and doing that from an effect body cascades a render before
  // the first paint.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => setNow(nowTimeInDhaka()), CLOCK_TICK_MS);
    return () => clearInterval(timer);
  }, []);

  // The week does not fit across 360px, so Thursday's button starts off-screen —
  // and a strip that opens on Saturday while the list below shows Thursday reads
  // as a bug. Scrolls once the rows are in, since there is no strip before then.
  useEffect(() => {
    if (loading) return;
    dayStrip.current
      ?.querySelector('[aria-pressed="true"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [loading, day]);

  /** `day:period` to the lesson there. At most one: the database forbids a
   *  teacher two lessons in one hour, which is what makes this a plain map. */
  const cells = useMemo(() => {
    const map = new Map<string, ClassRoutine>();
    for (const row of rows) map.set(`${row.day_of_week}:${row.period}`, row);
    return map;
  }, [rows]);

  /** The period the clock is inside, or null. Marked whether or not the teacher
   *  teaches in it — "you are free right now" is an answer too. */
  const livePeriodId = useMemo(() => {
    const live = periods.find(
      (p) => now >= p.start_time.slice(0, 5) && now < p.end_time.slice(0, 5),
    );
    return live?.id ?? null;
  }, [periods, now]);

  /** How heavy is my week — the question behind opening a timetable at all.
   *  A class and a section together make one teaching group: Class 5 · A and
   *  Class 5 · B are two rooms of students, not one. */
  const weekLoad = useMemo(() => {
    const groups = new Set<string>();
    const subjects = new Set<number>();
    for (const row of rows) {
      groups.add(`${row.academic_class}:${row.section ?? ''}`);
      subjects.add(row.subject);
    }
    return { periods: rows.length, groups: groups.size, subjects: subjects.size };
  }, [rows]);

  const where = (row: ClassRoutine) =>
    [lang === 'bn' ? row.class_name_bn || row.class_name : row.class_name, row.section_name]
      .filter(Boolean)
      .join(' · ');

  const subjectOf = (row: ClassRoutine) =>
    lang === 'bn' ? row.subject_name_bn || row.subject_name : row.subject_name;

  const cellBody = (row: ClassRoutine | undefined) =>
    row ? (
      <>
        <span className="block truncate text-sm font-medium text-gray-900">{subjectOf(row)}</span>
        <span className="block truncate text-xs text-gray-600">{where(row)}</span>
        {row.room && <span className="block truncate text-xs text-gray-400">{row.room}</span>}
      </>
    ) : (
      <span className="text-xs text-gray-300">{t('Free')}</span>
    );

  const breakLabel = (p: Period) => {
    // An institution that named the slot "Break" would otherwise read
    // "Break · Break · 9:45–10:15". The word is only prefixed when the period's
    // own name does not already carry it.
    const named = periodLabel(p);
    const head = named && named !== t('Break') ? `${t('Break')} · ${named}` : t('Break');
    return `${head} · ${shortTime(p.start_time)}–${shortTime(p.end_time)}`;
  };

  const liveBadge = (
    <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-[11px] font-medium text-blue-700">
      <span aria-hidden>●</span>
      {t('Now')}
    </span>
  );

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('My routine')}</h1>
        <p className="mt-1 text-sm text-gray-500">
          {[user?.name_bn || user?.name, sessionName].filter(Boolean).join(' · ')}
        </p>
      </header>

      {error && <FormError message={error} />}
      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {!loading && !error && rows.length === 0 && (
        // Named, not blank: somebody with no rows needs to know this is another
        // person's job to fix, and whose.
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
          <p className="text-sm font-medium text-gray-900">
            {t('No classes have been assigned to you yet.')}
          </p>
          <p className="mx-auto mt-2 max-w-md text-sm text-gray-500">
            {t('The office builds the weekly routine under Academics → Routine. Ask them to add your periods.')}
          </p>
        </div>
      )}

      {!loading && rows.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatCard
              tone="blue"
              icon={<NavIcon name="clock" />}
              label={t('Periods a week')}
              value={weekLoad.periods}
            />
            <StatCard
              tone="green"
              icon={<NavIcon name="academics" />}
              label={t('Classes')}
              value={weekLoad.groups}
            />
            <StatCard
              tone="amber"
              icon={<NavIcon name="document" />}
              label={t('Subjects')}
              value={weekLoad.subjects}
            />
          </div>

          {/* Phone: one day at a time, opening on today. */}
          <div className="md:hidden">
            {/* The day strip scrolls inside itself; the body never scrolls
                sideways (§7a rule 1). */}
            <div ref={dayStrip} className="scroll-x -mx-1 mb-3 px-1">
              <div className="flex w-max gap-1">
                {WEEK_DAYS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => setDay(d.value)}
                    aria-pressed={day === d.value}
                    className={`min-h-[36px] whitespace-nowrap rounded-md px-3 text-[13px] font-medium transition-colors sm:min-h-[32px] ${
                      day === d.value
                        ? 'bg-blue-600 text-white'
                        : d.value === today
                          ? 'border border-blue-200 bg-blue-50 text-blue-700'
                          : 'border border-gray-200 bg-white text-gray-600'
                    }`}
                  >
                    {t(d.label)}
                  </button>
                ))}
              </div>
            </div>

            <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
              {periods.map((p) => {
                if (p.is_break) {
                  return (
                    <li
                      key={p.id}
                      className="bg-amber-50 px-4 py-2 text-xs font-medium text-amber-800"
                    >
                      {breakLabel(p)}
                    </li>
                  );
                }
                const live = day === today && p.id === livePeriodId;
                return (
                  <li
                    key={p.id}
                    className={`flex min-h-[64px] items-center gap-3 px-4 py-3 ${live ? 'bg-blue-50' : ''}`}
                  >
                    <span className="w-20 shrink-0">
                      <span className="block text-sm font-medium text-gray-900">
                        {periodLabel(p)}
                      </span>
                      <span className="block text-xs text-gray-400">
                        {shortTime(p.start_time)}–{shortTime(p.end_time)}
                      </span>
                      {live && liveBadge}
                    </span>
                    <span className="min-w-0 flex-1">{cellBody(cells.get(`${day}:${p.id}`))}</span>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* md and up: the printed week. */}
          <div className="scroll-x hidden rounded-xl border border-gray-100 bg-white shadow-sm md:block">
            <table className="min-w-full border-collapse">
              <thead>
                <tr>
                  {/* Sticky, so the period stays readable while the days scroll
                      on a tablet. */}
                  <th className="sticky left-0 z-10 border-b border-gray-100 bg-white px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                    {t('Period')}
                  </th>
                  {WEEK_DAYS.map((d) => (
                    <th
                      key={d.value}
                      aria-current={d.value === today ? 'date' : undefined}
                      className={`border-b border-l border-gray-100 px-3 py-3 text-left text-xs font-medium uppercase tracking-wide ${
                        d.value === today ? 'bg-blue-50 text-blue-700' : 'text-gray-500'
                      }`}
                    >
                      {t(d.label)}
                      {d.value === today && (
                        <span className="ml-1 font-normal normal-case">{`· ${t('Today')}`}</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {periods.map((p) => {
                  if (p.is_break) {
                    // One band across the week rather than seven identical
                    // cells: a break belongs to the institution, not to a slot.
                    return (
                      <tr key={p.id} className="border-b border-gray-100">
                        <th className="sticky left-0 z-10 bg-amber-50 px-3 py-2 text-left text-xs font-medium text-amber-800">
                          {periodLabel(p)}
                        </th>
                        <td
                          colSpan={WEEK_DAYS.length}
                          className="bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800"
                        >
                          {breakLabel(p)}
                        </td>
                      </tr>
                    );
                  }
                  const live = p.id === livePeriodId;
                  return (
                    <tr key={p.id} className="border-b border-gray-100 last:border-0">
                      <th
                        className={`sticky left-0 z-10 px-3 py-2 text-left align-top ${
                          live ? 'bg-blue-50' : 'bg-white'
                        }`}
                      >
                        <span className="block text-sm font-medium text-gray-900">
                          {periodLabel(p)}
                        </span>
                        <span className="block text-xs text-gray-400">
                          {shortTime(p.start_time)}–{shortTime(p.end_time)}
                        </span>
                        {live && liveBadge}
                      </th>
                      {WEEK_DAYS.map((d) => {
                        const row = cells.get(`${d.value}:${p.id}`);
                        // Today's column is tinted; the cell where today meets
                        // the live period is tinted harder — at 10am that one
                        // cell is the whole point of the screen.
                        const tint =
                          d.value === today && live
                            ? 'bg-blue-100'
                            : d.value === today
                              ? 'bg-blue-50'
                              : '';
                        return (
                          <td
                            key={d.value}
                            className={`border-l border-gray-100 px-3 py-2 align-top ${tint}`}
                          >
                            <div className="flex min-h-[64px] flex-col justify-center">
                              {cellBody(row)}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap gap-2">
            <Link to="/" className={btnSecondary}>
              {t('Today’s classes')}
            </Link>
            <Link to="/attendance" className={btnSecondary}>
              {t('Month register')}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
