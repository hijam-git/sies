import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { ExamSchedule, StudentResult, Tabulation, TabulationRow } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, selectCls } from '../common/styles';
import { classLabel, examLabel } from './shared';
import type { ExamsData } from './shared';

/**
 * Results — the class tabulation sheet, one student's marksheet, and Publish.
 *
 * **Publishing is the whole point of this screen and the reason it is gated
 * separately** (`docs/02` §2.1). A teacher enters marks; only a principal
 * publishes, and publishing is the moment results become visible to students
 * through `/api/me/`. So the button appears only with `exams.publish`, and it
 * asks first — in a sentence that says what will happen, not "are you sure".
 *
 * Before publication the sheet is drawn anyway, marked plainly as **not visible
 * to students**. Staff need to read it in order to decide whether it is fit to
 * publish; what they must never do is publish it by accident, which is a
 * different problem and is solved by the confirm.
 *
 * There is no unpublish: `status` is read-only on the API and only `publish/`
 * moves it. The confirm says so, because a teacher cannot correct a mark
 * afterwards — `save_marks` refuses a published exam.
 */

export default function ResultsTab({ data }: { data: ExamsData }) {
  const { t, lang } = useT();
  const { can } = usePermissions();

  const [examChoice, setExamChoice] = useState('');
  const [classChoice, setClassChoice] = useState('');
  const [schedules, setSchedules] = useState<ExamSchedule[]>([]);
  const [sheet, setSheet] = useState<Tabulation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [marksheet, setMarksheet] = useState<StudentResult | null>(null);
  const [marksheetError, setMarksheetError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [publishing, setPublishing] = useState(false);

  const mayPublish = can('exams', 'publish');

  const examId = data.exams.some((e) => String(e.id) === examChoice)
    ? examChoice
    : String(data.exams[0]?.id ?? '');
  const exam = data.exams.find((e) => String(e.id) === examId);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (!examId) {
        setSchedules([]);
        return;
      }
      void apiClient
        .listAll<ExamSchedule>('/exam-schedules/', `?exam=${examId}`)
        .then(setSchedules)
        .catch(() => setSchedules([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [examId]);

  const paperClasses = useMemo(() => {
    const ids = new Set(schedules.map((s) => String(s.academic_class)));
    return data.classes.filter((c) => ids.has(String(c.id)));
  }, [schedules, data.classes]);

  const classId = paperClasses.some((c) => String(c.id) === classChoice)
    ? classChoice
    : String(paperClasses[0]?.id ?? '');

  /** The subject columns of the sheet — the class's own papers, in the order
   *  they were sat. */
  const subjectColumns = useMemo(
    () =>
      schedules
        .filter((s) => String(s.academic_class) === classId)
        .map((s) => ({ id: s.subject, name: s.subject_name, full: Number(s.full_marks) })),
    [schedules, classId],
  );

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
      setSheet(null);
      setError(apiErrorText(err, t, t('Could not load the tabulation sheet.')));
    } finally {
      setLoading(false);
    }
  }, [examId, classId, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const openMarksheet = async (row: TabulationRow) => {
    if (!exam) return;
    setMarksheetError(null);
    setMarksheet(null);
    try {
      setMarksheet(await apiClient.getStudentResult(exam.id, row.student));
    } catch (err) {
      // Before publication the server answers 404 for a student reading their
      // own; for staff it is a real failure, and either way the sentence it
      // sent is the honest one.
      setMarksheetError(apiErrorText(err, t, t('Could not load this marksheet.')));
    }
  };

  const publish = async () => {
    if (!exam) return;
    setPublishing(true);
    try {
      await apiClient.publishExam(exam.id);
      setConfirming(false);
      await data.reloadExams();
      await load();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not publish these results.')));
      setConfirming(false);
    } finally {
      setPublishing(false);
    }
  };

  const isPublished = exam?.status === 'published';

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Exam')}</span>
          <select value={examId} onChange={(e) => setExamChoice(e.target.value)} className={selectCls}>
            {data.exams.length === 0 && <option value="">{t('No exams yet.')}</option>}
            {data.exams.map((e) => (
              <option key={e.id} value={e.id}>
                {examLabel(e)}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Class')}</span>
          <select value={classId} onChange={(e) => setClassChoice(e.target.value)} className={selectCls}>
            {paperClasses.length === 0 && <option value="">{t('No papers scheduled yet.')}</option>}
            {paperClasses.map((c) => (
              <option key={c.id} value={c.id}>
                {classLabel(c)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <FormError message={error} />}

      {/* The visibility state, said plainly on the screen rather than implied
          by a badge colour. */}
      <div
        className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 text-sm ${
          isPublished
            ? 'border-green-200 bg-green-50 text-green-800'
            : 'border-amber-200 bg-amber-50 text-amber-900'
        }`}
      >
        <span>
          {isPublished
            ? t('Published — students can see these results.')
            : t('Not published — students cannot see these marks yet.')}
        </span>
        {mayPublish && !isPublished && exam && (
          <button type="button" onClick={() => setConfirming(true)} className={btnPrimary}>
            {t('Publish results')}
          </button>
        )}
      </div>

      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {sheet && sheet.rows.length === 0 && !loading && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('No students are enrolled in this class.')}
        </div>
      )}

      {sheet && sheet.rows.length > 0 && (
        <div className="scroll-x rounded-xl border border-gray-100 bg-white shadow-sm">
          <table className="min-w-full border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 min-w-[9rem] border-b border-r border-gray-200 bg-white px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                  {t('Student')}
                </th>
                {subjectColumns.map((column) => (
                  <th
                    key={column.id}
                    className="border-b border-gray-100 px-2 py-2 text-center text-xs font-medium text-gray-600"
                  >
                    <span className="block">{column.name}</span>
                    <span className="block text-[10px] font-normal text-gray-400">{column.full}</span>
                  </th>
                ))}
                <th className="border-b border-l border-gray-200 px-2 py-2 text-center text-xs font-medium uppercase tracking-wide text-gray-500">
                  {t('Total')}
                </th>
                <th className="border-b border-gray-100 px-2 py-2 text-center text-xs font-medium uppercase tracking-wide text-gray-500">
                  {t('Grade')}
                </th>
                <th className="border-b border-gray-100 px-2 py-2 text-center text-xs font-medium uppercase tracking-wide text-gray-500">
                  {t('Rank')}
                </th>
              </tr>
            </thead>
            <tbody>
              {sheet.rows.map((row) => (
                <tr key={row.enrolment} className="border-b border-gray-100 last:border-0">
                  <th className="sticky left-0 z-10 min-w-[9rem] border-r border-gray-200 bg-white px-3 py-2 text-left">
                    <button
                      type="button"
                      onClick={() => void openMarksheet(row)}
                      className="block truncate text-sm font-medium text-blue-700 hover:underline"
                    >
                      {row.student_name}
                    </button>
                    <span className="block text-[11px] text-gray-400">{row.roll ?? ''}</span>
                  </th>
                  {subjectColumns.map((column) => {
                    const cell = row.marks[String(column.id)];
                    return (
                      <td key={column.id} className="px-2 py-2 text-center text-sm text-gray-900">
                        {!cell ? '—' : cell.is_absent ? t('Absent') : Number(cell.total)}
                      </td>
                    );
                  })}
                  <td className="border-l border-gray-200 px-2 py-2 text-center text-sm font-medium text-gray-900">
                    {`${Number(row.obtained_marks)} / ${Number(row.total_marks)}`}
                  </td>
                  <td className="px-2 py-2 text-center text-sm">
                    <span className={row.is_passed ? 'text-green-700' : 'text-red-700'}>
                      {lang === 'bn' ? row.grade_bn : row.grade}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-center text-sm text-gray-700">
                    {row.rank_in_class ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── One student's marksheet ─────────────────────────────────────── */}
      <BaseModal
        isOpen={marksheet !== null || marksheetError !== null}
        onClose={() => {
          setMarksheet(null);
          setMarksheetError(null);
        }}
        title={marksheet ? marksheet.student_name : t('Marksheet')}
        maxWidth="lg"
        footer={
          <button
            type="button"
            onClick={() => {
              setMarksheet(null);
              setMarksheetError(null);
            }}
            className={`${btnSecondary} w-full justify-center`}
          >
            {t('Close')}
          </button>
        }
      >
        {marksheetError && <FormError message={marksheetError} />}
        {marksheet && (
          <div className="space-y-3">
            {!marksheet.is_published && (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                {t('Not published — students cannot see these marks yet.')}
              </p>
            )}
            <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
              {marksheet.subjects.map((line) => (
                <li key={line.subject} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="min-w-0 text-sm text-gray-900">
                    {lang === 'bn' ? line.subject_name_bn || line.subject_name : line.subject_name}
                  </span>
                  <span className="shrink-0 text-sm">
                    <span className={line.is_passed ? 'text-gray-900' : 'text-red-700'}>
                      {line.is_absent ? t('Absent') : Number(line.total)}
                    </span>
                    <span className="text-gray-400">{` / ${Number(line.full_marks)}`}</span>
                  </span>
                </li>
              ))}
            </ul>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">{t('Total')}</dt>
              <dd className="text-right text-gray-900">
                {`${Number(marksheet.obtained_marks)} / ${Number(marksheet.total_marks)}`}
              </dd>
              <dt className="text-gray-500">{t('Percentage')}</dt>
              <dd className="text-right text-gray-900">{`${Number(marksheet.percentage)}%`}</dd>
              <dt className="text-gray-500">{t('GPA')}</dt>
              <dd className="text-right text-gray-900">{Number(marksheet.gpa)}</dd>
              <dt className="text-gray-500">{t('Grade')}</dt>
              <dd className="text-right text-gray-900">
                {lang === 'bn' ? marksheet.grade_bn : marksheet.grade}
              </dd>
              <dt className="text-gray-500">{t('Result')}</dt>
              <dd className={`text-right font-medium ${marksheet.is_passed ? 'text-green-700' : 'text-red-700'}`}>
                {marksheet.is_passed ? t('Passed') : t('Failed')}
              </dd>
            </dl>
            {marksheet.failed_subjects.length > 0 && (
              <p className="text-sm text-red-700">
                {`${t('Failed subjects')}: ${marksheet.failed_subjects.join(', ')}`}
              </p>
            )}
          </div>
        )}
      </BaseModal>

      {/* ── Publish confirm ─────────────────────────────────────────────── */}
      <BaseModal
        isOpen={confirming}
        onClose={() => setConfirming(false)}
        title={t('Publish results')}
        maxWidth="md"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setConfirming(false)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void publish()}
              disabled={publishing}
              className={`${btnPrimary} flex-1`}
            >
              {publishing ? t('Publishing…') : t('Publish')}
            </button>
          </div>
        }
      >
        <p className="text-sm text-gray-700">
          {t('Publishing makes these results visible to students, and marks can no longer be changed afterwards.')}
        </p>
        {exam && <p className="mt-2 text-sm font-medium text-gray-900">{examLabel(exam)}</p>}
      </BaseModal>
    </div>
  );
}
