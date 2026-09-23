import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../lib/api';
import type { ConductDuty, MyDayPeriod, PeriodState, ReportFrequency } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { apiErrorText } from '../lib/apiErrors';
import { FormError } from '../components/common/Field';
import { btnPrimary, btnSecondary } from '../components/common/styles';
import { formatDhakaDate, todayInDhaka } from '../lib/timezone';

/**
 * The teacher's today board (`docs/08` D7) — what a teacher sees instead of the
 * generic overview.
 *
 * Each card carries exactly what was asked for: period name, time, class,
 * section, subject and student count, plus the state, which is what makes the
 * board useful rather than decorative:
 *
 *     ✓ taken   ● live now   ○ upcoming   ! missed
 *
 * **The button is the server's decision, not this screen's.** `is_markable`
 * comes down per period from the attendance window
 * (`Branch.attendance_window_minutes`), and a missed period is still markable
 * for whoever holds `attendance.update`. Recomputing "has the window closed"
 * here would be a second copy of a rule each institution sets for itself, and
 * the two would disagree at exactly the wrong minute.
 *
 * Phone-first by construction: one column of full-width cards, the action
 * button the width of the card and at the bottom of it, where a thumb is.
 *
 * **Your reports** sits under the periods: every conduct sheet the office has
 * named this teacher responsible for (Settings → Reports), with how much of
 * this period's sheet is filled. Unfilled first, and the button opens that
 * exact sheet — class, শাখা, template and date already chosen — so being
 * told about a report and starting it are one tap apart.
 */

const FREQUENCY_LABEL: Record<ReportFrequency, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  term: 'Per term',
};

const STATE_MARK: Record<PeriodState, { glyph: string; label: string; className: string }> = {
  taken: { glyph: '✓', label: 'Taken', className: 'bg-green-100 text-green-700' },
  live: { glyph: '●', label: 'Live now', className: 'bg-blue-100 text-blue-700' },
  upcoming: { glyph: '○', label: 'Upcoming', className: 'bg-gray-100 text-gray-500' },
  missed: { glyph: '!', label: 'Missed', className: 'bg-amber-100 text-amber-800' },
};

export default function TeacherDashboard() {
  const { t, lang } = useT();
  const { user } = useAuth();
  const { can } = usePermissions();

  const [date, setDate] = useState(todayInDhaka());
  const [periods, setPeriods] = useState<MyDayPeriod[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const mayTake = can('attendance', 'take') || can('attendance', 'update');
  const mayViewConduct = can('conduct', 'view');
  const mayFillConduct = can('conduct', 'take') || can('conduct', 'update');

  const [duties, setDuties] = useState<ConductDuty[]>([]);
  const [dutiesError, setDutiesError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDutiesError(null);
    // Two requests, two failures: a broken report list must not hide the
    // periods a teacher is about to take attendance for.
    const [day, mine] = await Promise.allSettled([
      apiClient.getMyDay(date),
      mayViewConduct ? apiClient.getMyConductDuties(date) : Promise.resolve({ duties: [] }),
    ]);
    if (day.status === 'fulfilled') {
      setPeriods(day.value.periods);
    } else {
      setPeriods([]);
      setError(apiErrorText(day.reason, t, t('Could not load today’s classes.')));
    }
    if (mine.status === 'fulfilled') {
      setDuties(mine.value.duties);
    } else {
      setDuties([]);
      setDutiesError(apiErrorText(mine.reason, t, t('Could not load your reports.')));
    }
    setLoading(false);
  }, [date, mayViewConduct, t]);

  // Deferred by a tick, like the other list screens: `load` sets state
  // synchronously, and doing that from an effect body cascades a render before
  // the first paint.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  // A board that says "live now" has to stay true while it is on screen; a
  // teacher leaves this open through a period. One minute is often enough to be
  // wrong by, so the board re-reads itself every minute.
  useEffect(() => {
    if (date !== todayInDhaka()) return;
    const timer = setInterval(() => void load(), 60_000);
    return () => clearInterval(timer);
  }, [date, load]);

  const taken = periods.filter((p) => p.state === 'taken').length;
  const reportsLeft = duties.filter((d) => !d.is_done).length;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Today’s classes')}</h1>
          <p className="mt-1 text-sm text-gray-500">
            {`${user?.name_bn || user?.name || ''} · ${formatDhakaDate(`${date}T00:00:00`)}`}
          </p>
        </div>
        {periods.length > 0 && (
          <span className="text-sm font-medium text-gray-600">
            {`${taken} / ${periods.length} ${t('taken')}`}
          </span>
        )}
      </header>

      <label className="block sm:max-w-xs">
        <span className="mb-1 block text-sm font-medium text-gray-700">{t('Date')}</span>
        <input
          type="date"
          value={date}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          className="min-h-[44px] w-full rounded-lg border border-gray-200 bg-white px-3 text-base text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </label>

      {error && <FormError message={error} />}
      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {!loading && periods.length === 0 && !error && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Nothing is scheduled for you on this day.')}
        </div>
      )}

      <div className="space-y-3">
        {periods.map((period) => {
          const mark = STATE_MARK[period.state];
          const where = [
            period.class_name_bn || period.class_name,
            period.section_name,
          ]
            .filter(Boolean)
            .join(' · ');
          const subject = period.subject_name_bn || period.subject_name;
          const blocked = !period.is_markable
            ? lang === 'bn'
              ? period.reason_text_bn
              : period.reason_text
            : null;

          return (
            <article
              key={period.routine}
              className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate text-base font-semibold text-gray-900">
                    {period.period_name_bn || period.period_name}
                  </h2>
                  <p className="mt-0.5 text-sm text-gray-600">
                    {`${period.start_time}–${period.end_time}`}
                  </p>
                  <p className="mt-1 truncate text-sm text-gray-900">{where}</p>
                  <p className="truncate text-sm text-gray-500">{subject}</p>
                  <p className="mt-1 text-xs text-gray-400">
                    {`${period.student_count} ${t('students')}${period.room ? ` · ${period.room}` : ''}`}
                  </p>
                </div>
                <span
                  className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${mark.className}`}
                >
                  <span aria-hidden>{mark.glyph}</span>
                  {t(mark.label)}
                </span>
              </div>

              {/* Full width and at the foot of the card — this is tapped
                  standing up, in front of a class (`CLAUDE.md` §7a). */}
              <div className="mt-3">
                {mayTake && period.is_markable ? (
                  <Link
                    to={
                      `/attendance?tab=class&class=${period.class}` +
                      `&period=${period.period}` +
                      (period.section ? `&section=${period.section}` : '') +
                      (period.subject ? `&subject=${period.subject}` : '')
                    }
                    className={`${btnPrimary} flex w-full items-center justify-center`}
                  >
                    {period.state === 'taken' ? t('Correct attendance') : t('Take attendance')}
                  </Link>
                ) : (
                  <p className="text-xs text-gray-500">
                    {blocked ?? t('Attendance for this period cannot be taken now.')}
                  </p>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {mayViewConduct && (duties.length > 0 || dutiesError) && (
        <section className="space-y-3" aria-labelledby="your-reports">
          <div className="flex items-end justify-between gap-3 pt-2">
            <h2 id="your-reports" className="text-lg font-bold text-gray-900">
              {t('Your reports')}
            </h2>
            {duties.length > 0 && (
              <span className="text-sm font-medium text-gray-600">
                {reportsLeft > 0 ? `${reportsLeft} ${t('left to fill')}` : t('All filled')}
              </span>
            )}
          </div>

          {dutiesError && <FormError message={dutiesError} />}

          {duties.map((duty) => {
            const where = [
              lang === 'bn' ? duty.class_name_bn || duty.class_name : duty.class_name,
              duty.section_name || t('Whole class'),
            ].join(' · ');
            const pct = duty.student_count
              ? Math.round((duty.filled_count / duty.student_count) * 100)
              : 100;
            const link =
              `/conduct?tab=sheet&class=${duty.academic_class}` +
              `&template=${duty.template}&date=${date}` +
              (duty.section ? `&section=${duty.section}` : '');

            return (
              <article
                key={duty.assignment}
                className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold text-gray-900">
                      {(lang === 'bn' && duty.template_name_bn) || duty.template_name}
                    </h3>
                    <p className="mt-0.5 truncate text-sm text-gray-900">{where}</p>
                    <p className="text-xs text-gray-400">
                      {`${t(FREQUENCY_LABEL[duty.frequency])} · ${duty.period}`}
                    </p>
                  </div>
                  <span
                    className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                      duty.is_done ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    <span aria-hidden>{duty.is_done ? '✓' : '!'}</span>
                    {`${duty.filled_count} / ${duty.student_count}`}
                  </span>
                </div>

                <div
                  className="mt-3 h-1.5 overflow-hidden rounded-full bg-gray-100"
                  role="progressbar"
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={t('Filled')}
                >
                  <div
                    className={`h-full rounded-full ${duty.is_done ? 'bg-green-500' : 'bg-amber-500'}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>

                <div className="mt-3">
                  <Link
                    to={link}
                    className={`${
                      duty.is_done || !mayFillConduct ? btnSecondary : btnPrimary
                    } flex w-full items-center justify-center`}
                  >
                    {!mayFillConduct
                      ? t('View report')
                      : duty.is_done
                        ? t('Review report')
                        : duty.filled_count > 0
                          ? t('Finish report')
                          : t('Fill report')}
                  </Link>
                </div>
              </article>
            );
          })}
        </section>
      )}

      <div className="flex flex-wrap gap-2">
        <Link to="/attendance" className={btnSecondary}>
          {t('Month register')}
        </Link>
        <Link to="/exams?tab=marks" className={btnSecondary}>
          {t('Marks entry')}
        </Link>
      </div>
    </div>
  );
}
