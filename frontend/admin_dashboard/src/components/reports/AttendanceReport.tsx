import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass, MonthRegister, Session } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import { formatNumber, formatPercent } from '../../lib/format';
import type { Period } from '../../lib/period';
import ExportCsvButton from '../common/ExportCsvButton';
import FilterBar, { filterSelectCls } from '../common/FilterBar';
import ResponsiveTable from '../common/ResponsiveTable';
import { FormError } from '../common/Field';
import Picker from '../common/Picker';
import ReportStat from './ReportStat';
import { share } from './reportUtils';

/**
 * Attendance — the monthly percentage by class, and who is below the line
 * (`docs/02` §4.8).
 *
 * **Both are computed from the month register**, one request per class, because
 * that is the only endpoint that reads attendance: `attendance/urls.py` has
 * four paths and none of them aggregates. The register already returns each
 * student's present / absent / marked totals and the server's own percentage
 * rule (`late` counts as present, `half_day` as half, holidays excluded), so
 * summing those is the same arithmetic the grid shows — not a second definition
 * of "attendance percentage", which is exactly how two screens end up
 * disagreeing about the same class.
 *
 * The cost is a request per class. Acceptable for the twenty-odd classes an
 * institution has, and the honest fix is a summary endpoint rather than a
 * cleverer client.
 *
 * **Staff attendance is not here.** `DailyAttendance` stores teacher and
 * employee rows, but the register endpoint reads students only and there is no
 * endpoint that reads the others — so a staff attendance report cannot be built
 * from this API without one.
 */

const DEFAULTER_THRESHOLD = 0.75;

interface ClassRow {
  id: number;
  name: string;
  students: number;
  attended: number;
  marked: number;
  percent: number | null;
}

interface DefaulterRow {
  key: string;
  name: string;
  code: string;
  className: string;
  present: number;
  absent: number;
  marked: number;
  percent: number | null;
}

export default function AttendanceReport({
  period,
  sessions,
  classes,
  mayExport,
}: {
  period: Period;
  sessions: Session[];
  classes: AcademicClass[];
  mayExport: boolean;
}) {
  const { t } = useT();

  const [view, setView] = useState<'classes' | 'defaulters'>('classes');
  const [sessionId, setSessionId] = useState('');
  const [registers, setRegisters] = useState<MonthRegister[]>([]);
  /** Classes whose register did not load. They are dropped from the figures
   *  below, and a headline percentage computed over the survivors with no
   *  sign of it is the kind of wrong number nobody checks. */
  const [missing, setMissing] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const currentSession = useMemo(
    () => String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? ''),
    [sessions],
  );
  const session = sessionId || currentSession;

  /** The register is a MONTH, so a range period is read by the month it starts
   *  in. Saying so on the screen is better than silently answering a different
   *  question from the one the period control asks. */
  const month = useMemo(() => {
    if (period.mode === 'month') {
      return `${period.year}-${String(period.month).padStart(2, '0')}`;
    }
    if (period.mode === 'range') return period.from.slice(0, 7);
    return new Date().toISOString().slice(0, 7);
  }, [period]);

  const sessionClasses = useMemo(
    () => classes.filter((c) => !session || String(c.session) === session),
    [classes, session],
  );

  /* Every load here is keyed on a filter the user can change while the request
   * is in the air, and the slower of two answers wins by landing last. The
   * debounce below does not cover it — it only cancels a request that has not
   * started. `req` says whether this answer is still the one being waited for.
   */
  // `/attendance/register/` is addressed by CLASS, so it answers 404 while a
  // platform admin is looking at every institution at once — there is no
  // register of all of them. Every class then failed, the failures were
  // swallowed, and the report drew a confident zero. Asking for an institution
  // first is the honest screen.
  const { user, activeBranchId } = useAuth();
  const needsBranch = user?.branch === null && activeBranchId === null;

  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    if (needsBranch) {
      setRegisters([]);
      setMissing(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(
        sessionClasses.map((c) =>
          apiClient
            .getMonthRegister({ academicClass: c.id, month })
            .catch(() => null),
        ),
      );
      if (!req.isCurrent(mine)) return;
      setRegisters(results.filter((r): r is MonthRegister => r !== null));
      // A class whose register failed is dropped from the list above, and the
      // institution-wide percentage below is then computed over the survivors.
      // Saying how many are missing is the difference between an understated
      // figure and a wrong one.
      setMissing(results.filter((r) => r === null).length);
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setError(apiErrorText(err, t, t('Could not load this report.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [sessionClasses, month, needsBranch, req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const className = (id: number) => {
    const found = classes.find((c) => c.id === id);
    return found ? found.name_bn || found.name : String(id);
  };

  const classRows: ClassRow[] = useMemo(
    () =>
      registers.map((register) => {
        // `percent` per student is the server's; the class figure is the ratio
        // of attended days to marked days across the class, which is the only
        // way an average does not over-weight a student who joined mid-month.
        const attended = register.students.reduce(
          (sum, s) => sum + s.present + s.late + s.half_day * 0.5,
          0,
        );
        const marked = register.students.reduce((sum, s) => sum + s.marked_days, 0);
        return {
          id: register.class,
          name: className(register.class),
          students: register.students.length,
          attended,
          marked,
          percent: share(attended, marked),
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [registers, classes],
  );

  const defaulters: DefaulterRow[] = useMemo(
    () =>
      registers
        .flatMap((register) =>
          register.students.map((s) => ({
            key: `${register.class}-${s.student}`,
            name: s.name_bn || s.name,
            code: s.student_code,
            className: className(register.class),
            present: s.present,
            absent: s.absent,
            marked: s.marked_days,
            percent: s.percent === null ? null : s.percent / 100,
          })),
        )
        // A student with nothing marked is not a defaulter — they are a student
        // whose class has not taken attendance yet.
        .filter((r) => r.marked > 0 && r.percent !== null && r.percent < DEFAULTER_THRESHOLD)
        .sort((a, b) => (a.percent ?? 0) - (b.percent ?? 0)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [registers, classes],
  );

  const attended = classRows.reduce((sum, r) => sum + r.attended, 0);
  const marked = classRows.reduce((sum, r) => sum + r.marked, 0);

  return (
    <div className="space-y-4">
      <FilterBar active={view !== 'classes' || !!sessionId}>
        <select
          value={view}
          onChange={(e) => setView(e.target.value as 'classes' | 'defaulters')}
          aria-label={t('Report')}
          className={filterSelectCls}
        >
          <option value="classes">{t('Monthly percentage by class')}</option>
          <option value="defaulters">{t('Defaulter list')}</option>
        </select>
        <Picker
          value={session}
          onChange={setSessionId}
          options={sessions.map((s) => ({ value: String(s.id), label: s.name }))}
          aria-label={t('Session')}
          className={filterSelectCls}
        />
      </FilterBar>

      <p className="text-sm text-gray-500">
        {`${t('Attendance is kept by month, so this report reads')} ${month}.`}
      </p>

      <FormError message={error} />

      {needsBranch && (
        <p className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">
          {t('Choose an institution in the header to read its registers.')}
        </p>
      )}

      {missing > 0 && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {`${formatNumber(missing)} ${t('classes could not be read, and are not in these figures.')}`}
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ReportStat label={t('Classes')} value={formatNumber(classRows.length)} />
        <ReportStat label={t('Days marked')} value={formatNumber(marked)} />
        <ReportStat
          label={t('Attendance')}
          value={formatPercent(share(attended, marked))}
          sub={`${t('Below')} ${Math.round(DEFAULTER_THRESHOLD * 100)}%: ${formatNumber(defaulters.length)}`}
        />
      </div>

      {view === 'classes' && (
        <>
          {mayExport && (
            <ExportCsvButton
              filename={`attendance-${month}.csv`}
              rows={() => [
                [t('Class'), t('Students'), t('Days marked'), t('Attendance')],
                ...classRows.map((r) => [r.name, r.students, r.marked, formatPercent(r.percent)]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'class', label: t('Class'), primary: true, render: (r: ClassRow) => r.name },
              { key: 'students', label: t('Students'), render: (r: ClassRow) => formatNumber(r.students) },
              { key: 'marked', label: t('Days marked'), hideOnNarrow: true, render: (r: ClassRow) => formatNumber(r.marked) },
              { key: 'percent', label: t('Attendance'), render: (r: ClassRow) => formatPercent(r.percent) },
            ]}
            rows={classRows}
            rowKey={(r) => r.id}
            empty={loading ? t('Loading…') : t('No attendance has been taken for this month.')}
          />
        </>
      )}

      {view === 'defaulters' && (
        <>
          {mayExport && (
            <ExportCsvButton
              filename={`attendance-defaulters-${month}.csv`}
              rows={() => [
                [t('Student'), t('Student ID'), t('Class'), t('Present'), t('Absent'), t('Attendance')],
                ...defaulters.map((r) => [
                  r.name,
                  r.code,
                  r.className,
                  r.present,
                  r.absent,
                  formatPercent(r.percent),
                ]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'student', label: t('Student'), primary: true, render: (r: DefaulterRow) => r.name },
              { key: 'code', label: t('Student ID'), hideOnNarrow: true, render: (r: DefaulterRow) => r.code },
              { key: 'class', label: t('Class'), render: (r: DefaulterRow) => r.className },
              { key: 'absent', label: t('Absent'), render: (r: DefaulterRow) => formatNumber(r.absent) },
              { key: 'percent', label: t('Attendance'), render: (r: DefaulterRow) => formatPercent(r.percent) },
            ]}
            rows={defaulters}
            rowKey={(r) => r.key}
            empty={loading ? t('Loading…') : t('Nobody is below the line this month.')}
          />
        </>
      )}
    </div>
  );
}
