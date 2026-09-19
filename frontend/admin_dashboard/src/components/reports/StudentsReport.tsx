import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass, Admission, Enrolment, Section, Session, Stream } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import { formatNumber } from '../../lib/format';
import type { Period } from '../../lib/period';
import { periodLabel } from '../../lib/period';
import ExportCsvButton from '../common/ExportCsvButton';
import FilterBar, { filterSelectCls } from '../common/FilterBar';
import PeriodFilter from '../common/PeriodFilter';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { FormError } from '../common/Field';
import Picker from '../common/Picker';
import ReportStat from './ReportStat';
import { groupBy, inPeriod, monthOf, periodRange } from './reportUtils';

/**
 * Students — strength, admissions over a period, and withdrawals (`docs/02` §4.8).
 *
 * **Strength is counted from the enrolment register, not from `Student`.** A
 * student's class is a property of the session they are enrolled in, not of
 * their record (that is the whole shape of `academics`), so "how many in class
 * 5" is a question only the register can answer — and a student who left in
 * March is still a `Student` row.
 */

type View = 'strength' | 'admissions' | 'withdrawals';

/** The two ways a student leaves, as a reader would say them. The raw enum was
 *  being printed straight onto the screen and into the CSV, in both
 *  languages — `withdrawn`, in a Bengali report. */
const LEAVING_LABEL: Record<string, string> = {
  withdrawn: 'Withdrawn',
  transferred: 'Transferred',
};

interface StrengthRow {
  key: string;
  className: string;
  sectionName: string;
  streamName: string;
  count: number;
  boys: number;
  girls: number;
}

export default function StudentsReport({
  period,
  onPeriod,
  sessions,
  classes,
  sections,
  streams,
  mayExport,
}: {
  period: Period;
  onPeriod: (p: Period) => void;
  sessions: Session[];
  classes: AcademicClass[];
  sections: Section[];
  streams: Stream[];
  mayExport: boolean;
}) {
  const { t } = useT();

  const [view, setView] = useState<View>('strength');
  const [sessionId, setSessionId] = useState('');
  const [enrolments, setEnrolments] = useState<Enrolment[]>([]);
  const [admissions, setAdmissions] = useState<Admission[]>([]);
  const [students, setStudents] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const currentSession = useMemo(
    () => String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? ''),
    [sessions],
  );
  const session = sessionId || currentSession;

  /* The filter can change while the request is in the air, and the slower of
   * two answers wins by landing last — under the new heading. `req` says
   * whether this answer is still the one being waited for. */
  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    setLoading(true);
    setError(null);
    try {
      const query = session ? `?session=${session}` : '';
      const [enrolmentRows, admissionRows] = await Promise.all([
        apiClient.listAll<Enrolment>('/enrolments/', query),
        apiClient.listAll<Admission>('/admissions/', query).catch(() => [] as Admission[]),
      ]);
      if (!req.isCurrent(mine)) return;
      setEnrolments(enrolmentRows);
      setAdmissions(admissionRows);
      // Gender comes from the student record, not the enrolment, and the boys /
      // girls split is what an institution's strength report is read for.
      setStudents(
        Object.fromEntries(
          (await apiClient
            .listAll<{ id: number; gender: string }>('/students/', '?is_active=true')
            .catch(() => []))
            .map((s) => [s.id, s.gender]),
        ),
      );
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setError(apiErrorText(err, t, t('Could not load this report.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [session, req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const className = (id: number) => {
    const found = classes.find((c) => c.id === id);
    return found ? found.name_bn || found.name : String(id);
  };
  const sectionName = (id: number | null) => {
    const found = sections.find((s) => s.id === id);
    return found ? found.name_bn || found.name : '—';
  };
  const streamName = (id: number) => {
    const cls = classes.find((c) => c.id === id);
    const found = streams.find((s) => s.id === cls?.stream);
    return found ? found.name_bn || found.name : '—';
  };

  const strength: StrengthRow[] = useMemo(() => {
    const active = enrolments.filter((e) => e.status === 'active' && e.is_active);
    return [...groupBy(active, (e) => `${e.academic_class}:${e.section ?? 0}`).entries()]
      .map(([key, rows]) => ({
        key,
        className: className(rows[0].academic_class),
        sectionName: sectionName(rows[0].section),
        streamName: streamName(rows[0].academic_class),
        count: rows.length,
        boys: rows.filter((r) => students[r.student] === 'male').length,
        girls: rows.filter((r) => students[r.student] === 'female').length,
      }))
      .sort((a, b) => a.className.localeCompare(b.className));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enrolments, students, classes, sections, streams]);

  const range = periodRange(period);

  const admissionRows = useMemo(() => {
    const inside = admissions.filter((a) => inPeriod(a.created_at, range));
    return [...groupBy(inside, (a) => monthOf(a.created_at)).entries()]
      .map(([month, rows]) => ({
        month,
        applied: rows.length,
        admitted: rows.filter((r) => r.status === 'admitted').length,
        rejected: rows.filter((r) => r.status === 'rejected').length,
        pending: rows.filter((r) => ['pending', 'interview', 'accepted'].includes(r.status)).length,
      }))
      .sort((a, b) => a.month.localeCompare(b.month));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [admissions, period]);

  const withdrawals = useMemo(
    () =>
      enrolments
        .filter((e) => e.status === 'withdrawn' || e.status === 'transferred')
        .filter((e) => inPeriod(e.left_on ?? e.enrolled_on, range)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enrolments, period],
  );

  const strengthColumns: Column<StrengthRow>[] = [
    { key: 'class', label: t('Class'), primary: true, render: (r) => r.className },
    { key: 'section', label: t('Section'), render: (r) => r.sectionName },
    { key: 'stream', label: t('Stream'), hideOnNarrow: true, render: (r) => r.streamName },
    { key: 'boys', label: t('Boys'), render: (r) => formatNumber(r.boys) },
    { key: 'girls', label: t('Girls'), render: (r) => formatNumber(r.girls) },
    { key: 'count', label: t('Strength'), render: (r) => formatNumber(r.count) },
  ];

  const total = strength.reduce((sum, row) => sum + row.count, 0);

  return (
    <div className="space-y-4">
      <FilterBar
        period={<PeriodFilter value={period} onChange={onPeriod} allowAllTime />}
        active={view !== 'strength' || !!sessionId}
      >
        <select
          value={view}
          onChange={(e) => setView(e.target.value as View)}
          aria-label={t('Report')}
          className={filterSelectCls}
        >
          <option value="strength">{t('Strength by class')}</option>
          <option value="admissions">{t('Admissions over a period')}</option>
          <option value="withdrawals">{t('Withdrawals')}</option>
        </select>
        <Picker
          value={session}
          onChange={setSessionId}
          options={sessions.map((s) => ({ value: String(s.id), label: s.name }))}
          aria-label={t('Session')}
          className={filterSelectCls}
        />
      </FilterBar>

      <FormError message={error} />

      {view === 'strength' && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <ReportStat label={t('On the roll')} value={formatNumber(total)} />
            <ReportStat
              label={t('Boys')}
              value={formatNumber(strength.reduce((s, r) => s + r.boys, 0))}
            />
            <ReportStat
              label={t('Girls')}
              value={formatNumber(strength.reduce((s, r) => s + r.girls, 0))}
            />
          </div>

          {mayExport && (
            <ExportCsvButton
              filename={`strength-${session}.csv`}
              rows={() => [
                [t('Class'), t('Section'), t('Stream'), t('Boys'), t('Girls'), t('Strength')],
                ...strength.map((r) => [r.className, r.sectionName, r.streamName, r.boys, r.girls, r.count]),
              ]}
            />
          )}

          <ResponsiveTable
            columns={strengthColumns}
            rows={strength}
            rowKey={(r) => r.key}
            empty={loading ? t('Loading…') : t('Nobody is enrolled in this session yet.')}
          />
        </>
      )}

      {view === 'admissions' && (
        <>
          <p className="text-sm text-gray-500">{`${t('Applications')} · ${periodLabel(period, t)}`}</p>
          {mayExport && (
            <ExportCsvButton
              filename="admissions.csv"
              rows={() => [
                [t('Month'), t('Applied'), t('Admitted'), t('Rejected'), t('Pending')],
                ...admissionRows.map((r) => [r.month, r.applied, r.admitted, r.rejected, r.pending]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'month', label: t('Month'), primary: true, render: (r) => r.month },
              { key: 'applied', label: t('Applied'), render: (r) => formatNumber(r.applied) },
              { key: 'admitted', label: t('Admitted'), render: (r) => formatNumber(r.admitted) },
              { key: 'rejected', label: t('Rejected'), render: (r) => formatNumber(r.rejected) },
              { key: 'pending', label: t('Pending'), render: (r) => formatNumber(r.pending) },
            ]}
            rows={admissionRows}
            rowKey={(r) => r.month}
            empty={loading ? t('Loading…') : t('No applications in this period.')}
          />
        </>
      )}

      {view === 'withdrawals' && (
        <>
          {mayExport && (
            <ExportCsvButton
              filename="withdrawals.csv"
              rows={() => [
                [t('Student'), t('Class'), t('Status'), t('Left on')],
                ...withdrawals.map((e) => [
                  e.student_name,
                  className(e.academic_class),
                  t(LEAVING_LABEL[e.status] ?? e.status),
                  e.left_on ?? '',
                ]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'student', label: t('Student'), primary: true, render: (e) => e.student_name },
              { key: 'class', label: t('Class'), render: (e) => className(e.academic_class) },
              { key: 'status', label: t('Status'), render: (e) => t(LEAVING_LABEL[e.status] ?? e.status) },
              { key: 'left', label: t('Left on'), render: (e) => e.left_on ?? '—' },
            ]}
            rows={withdrawals}
            rowKey={(e) => e.id}
            empty={loading ? t('Loading…') : t('Nobody withdrew in this period.')}
          />
        </>
      )}
    </div>
  );
}
