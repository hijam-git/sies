import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass, Exam, Subject, Tabulation, TabulationRow } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { formatNumber, formatPercent } from '../../lib/format';
import ExportCsvButton from '../common/ExportCsvButton';
import FilterBar, { filterSelectCls } from '../common/FilterBar';
import ResponsiveTable from '../common/ResponsiveTable';
import { FormError } from '../common/Field';
import ReportStat from './ReportStat';
import { share } from './reportUtils';

/**
 * Exams — the tabulation sheet, the merit list and the subject analysis
 * (`docs/02` §4.8).
 *
 * **All three are one request.** `GET /api/exams/<id>/tabulation/` returns
 * every student, every subject cell, the percentage, the grade and the rank —
 * computed by the server, which is where the pass rule and the grade scale
 * live. The merit list is that sheet ordered by rank; the subject analysis is
 * the same cells counted per subject. Re-deriving a grade here would be a
 * second grade scale, and the two would part company the first time somebody
 * changed the pass mark.
 */

type View = 'tabulation' | 'merit' | 'subjects';

export default function ExamsReport({
  classes,
  mayExport,
}: {
  classes: AcademicClass[];
  mayExport: boolean;
}) {
  const { t } = useT();

  const [view, setView] = useState<View>('tabulation');
  const [exams, setExams] = useState<Exam[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [examId, setExamId] = useState('');
  const [classId, setClassId] = useState('');
  const [sheet, setSheet] = useState<Tabulation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      void apiClient
        .listAll<Exam>('/exams/', '?ordering=-starts_on')
        .then((rows) => {
          setExams(rows);
          setExamId((current) => current || String(rows[0]?.id ?? ''));
        })
        .catch(() => setExams([]))
        .finally(() => setLoading(false));
      void apiClient
        .listAll<Subject>('/subjects/', '')
        .then(setSubjects)
        .catch(() => setSubjects([]));
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  const load = useCallback(async () => {
    if (!examId || !classId) {
      setSheet(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setSheet(await apiClient.getTabulation(Number(examId), Number(classId)));
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not load this report.')));
      setSheet(null);
    } finally {
      setLoading(false);
    }
  }, [examId, classId, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  // Memoised rather than `sheet?.rows ?? []`: the fallback would be a new empty
  // array on every render, and everything below derives from it.
  const rows = useMemo(() => sheet?.rows ?? [], [sheet]);

  const merit = useMemo(
    () =>
      [...rows]
        .filter((r) => r.rank_in_class !== null)
        .sort((a, b) => (a.rank_in_class ?? 0) - (b.rank_in_class ?? 0)),
    [rows],
  );

  const subjectName = (id: string) => {
    const found = subjects.find((s) => String(s.id) === id);
    return found ? found.name_bn || found.name : id;
  };

  /** Per subject: how many sat it, how many passed the whole exam having sat
   *  it, the average mark and the highest. Absence is counted, not silently
   *  dropped — an empty seat is the thing a subject analysis is read for. */
  const subjectRows = useMemo(() => {
    const ids = new Set<string>();
    rows.forEach((r) => Object.keys(r.marks).forEach((id) => ids.add(id)));
    return [...ids].map((id) => {
      const cells = rows.map((r) => r.marks[id]).filter(Boolean);
      const sat = cells.filter((c) => !c.is_absent);
      const totals = sat.map((c) => Number(c.total));
      return {
        id,
        name: subjectName(id),
        entered: cells.length,
        absent: cells.length - sat.length,
        average: sat.length ? totals.reduce((a, b) => a + b, 0) / sat.length : null,
        highest: sat.length ? Math.max(...totals) : null,
      };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, subjects]);

  const passed = rows.filter((r) => r.is_passed).length;

  return (
    <div className="space-y-4">
      <FilterBar active={view !== 'tabulation'}>
        <select
          value={view}
          onChange={(e) => setView(e.target.value as View)}
          aria-label={t('Report')}
          className={filterSelectCls}
        >
          <option value="tabulation">{t('Tabulation')}</option>
          <option value="merit">{t('Merit list')}</option>
          <option value="subjects">{t('Subject analysis')}</option>
        </select>
        <select
          value={examId}
          onChange={(e) => setExamId(e.target.value)}
          aria-label={t('Exam')}
          className={filterSelectCls}
        >
          <option value="">{t('Choose an exam')}</option>
          {exams.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name_bn || x.name}
            </option>
          ))}
        </select>
        <select
          value={classId}
          onChange={(e) => setClassId(e.target.value)}
          aria-label={t('Class')}
          className={filterSelectCls}
        >
          <option value="">{t('Choose a class')}</option>
          {classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name_bn || c.name}
            </option>
          ))}
        </select>
      </FilterBar>

      <FormError message={error} />

      {!classId && (
        <p className="rounded-xl border border-gray-100 bg-white p-6 text-center text-sm text-gray-500 shadow-sm">
          {t('Choose an exam and a class.')}
        </p>
      )}

      {classId && (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <ReportStat label={t('Students')} value={formatNumber(rows.length)} />
            <ReportStat label={t('Passed')} value={formatNumber(passed)} />
            <ReportStat
              label={t('Pass rate')}
              value={formatPercent(share(passed, rows.length))}
              sub={sheet?.is_published ? t('Published') : t('Not published')}
            />
          </div>

          {view === 'tabulation' && (
            <>
              {mayExport && (
                <ExportCsvButton
                  filename="tabulation.csv"
                  rows={() => [
                    [t('Roll'), t('Student'), t('Total'), t('Percentage'), t('Grade'), t('Rank')],
                    ...rows.map((r) => [
                      r.roll ?? '',
                      r.student_name,
                      r.obtained_marks,
                      r.percentage,
                      r.grade,
                      r.rank_in_class ?? '',
                    ]),
                  ]}
                />
              )}
              <ResponsiveTable
                columns={[
                  { key: 'roll', label: t('Roll'), render: (r: TabulationRow) => r.roll ?? '—' },
                  { key: 'student', label: t('Student'), primary: true, render: (r: TabulationRow) => r.student_name },
                  { key: 'obtained', label: t('Total'), render: (r: TabulationRow) => r.obtained_marks },
                  { key: 'percentage', label: t('Percentage'), hideOnNarrow: true, render: (r: TabulationRow) => `${r.percentage}%` },
                  { key: 'grade', label: t('Grade'), render: (r: TabulationRow) => r.grade_bn || r.grade },
                  { key: 'rank', label: t('Rank'), render: (r: TabulationRow) => r.rank_in_class ?? '—' },
                ]}
                rows={rows}
                rowKey={(r) => r.enrolment}
                empty={loading ? t('Loading…') : t('No marks have been entered for this class.')}
              />
            </>
          )}

          {view === 'merit' && (
            <>
              {mayExport && (
                <ExportCsvButton
                  filename="merit-list.csv"
                  rows={() => [
                    [t('Rank'), t('Roll'), t('Student'), t('Total'), t('Percentage'), t('Grade')],
                    ...merit.map((r) => [
                      r.rank_in_class ?? '',
                      r.roll ?? '',
                      r.student_name,
                      r.obtained_marks,
                      r.percentage,
                      r.grade,
                    ]),
                  ]}
                />
              )}
              <ResponsiveTable
                columns={[
                  { key: 'rank', label: t('Rank'), render: (r: TabulationRow) => r.rank_in_class ?? '—' },
                  { key: 'student', label: t('Student'), primary: true, render: (r: TabulationRow) => r.student_name },
                  { key: 'roll', label: t('Roll'), hideOnNarrow: true, render: (r: TabulationRow) => r.roll ?? '—' },
                  { key: 'obtained', label: t('Total'), render: (r: TabulationRow) => r.obtained_marks },
                  { key: 'grade', label: t('Grade'), render: (r: TabulationRow) => r.grade_bn || r.grade },
                ]}
                rows={merit}
                rowKey={(r) => r.enrolment}
                empty={loading ? t('Loading…') : t('Nobody has passed this exam yet.')}
              />
            </>
          )}

          {view === 'subjects' && (
            <>
              {mayExport && (
                <ExportCsvButton
                  filename="subject-analysis.csv"
                  rows={() => [
                    [t('Subject'), t('Marks entered'), t('Absent'), t('Average'), t('Highest')],
                    ...subjectRows.map((r) => [
                      r.name,
                      r.entered,
                      r.absent,
                      r.average === null ? '' : r.average.toFixed(2),
                      r.highest ?? '',
                    ]),
                  ]}
                />
              )}
              <ResponsiveTable
                columns={[
                  { key: 'subject', label: t('Subject'), primary: true, render: (r: (typeof subjectRows)[number]) => r.name },
                  { key: 'entered', label: t('Marks entered'), render: (r: (typeof subjectRows)[number]) => formatNumber(r.entered) },
                  { key: 'absent', label: t('Absent'), render: (r: (typeof subjectRows)[number]) => formatNumber(r.absent) },
                  { key: 'average', label: t('Average'), render: (r: (typeof subjectRows)[number]) => (r.average === null ? '—' : r.average.toFixed(2)) },
                  { key: 'highest', label: t('Highest'), hideOnNarrow: true, render: (r: (typeof subjectRows)[number]) => r.highest ?? '—' },
                ]}
                rows={subjectRows}
                rowKey={(r) => r.id}
                empty={loading ? t('Loading…') : t('No marks have been entered for this class.')}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}
