import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { apiClient } from '../../lib/api';
import type { Enrolment, ExamSchedule, Mark, MarkRowInput } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, selectCls } from '../common/styles';
import { classLabel, examLabel, marksInputValue, subjectLabel } from './shared';
import type { ExamsData } from './shared';

/**
 * Marks entry — one class × one subject, as a grid.
 *
 * **Deliberately the same interaction model as the attendance register**
 * (`docs/02` §6): students down the side, one input per row, Enter and the
 * arrows move down the column, and the whole grid is batch-saved in one
 * request. A teacher learns one grid and knows both.
 *
 * **Resumable.** Marks already entered come back from `/marks/` and fill the
 * boxes, so a teacher who did half the class yesterday sees the half they did.
 * The save is idempotent — keyed on `(exam, student, subject)` — so pressing
 * Save twice on a slow connection writes the same rows rather than doubling a
 * total, which is what a teacher on a phone actually does.
 *
 * **The row is keyed on the ENROLMENT, not the student.** A student who
 * repeated a year has two, and only the enrolment says which year's mark this
 * is; that is the key `POST /exams/<id>/marks/` takes.
 *
 * No separate phone mode: one number per row is naturally narrow, so the same
 * vertical list works at 360px (`CLAUDE.md` §7a) — with `inputMode="numeric"`
 * so the keypad comes up rather than the alphabet.
 */

interface RowDraft {
  obtained: string;
  practical: string;
  absent: boolean;
}

export default function MarksEntryTab({ data }: { data: ExamsData }) {
  const { t } = useT();
  const { can } = usePermissions();

  const [examChoice, setExamChoice] = useState('');
  const [classChoice, setClassChoice] = useState('');
  const [subjectChoice, setSubjectChoice] = useState('');

  const [schedules, setSchedules] = useState<ExamSchedule[]>([]);
  const [enrolments, setEnrolments] = useState<Enrolment[]>([]);
  const [rows, setRows] = useState<Map<number, RowDraft>>(new Map());
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const inputRefs = useRef(new Map<number, HTMLInputElement>());

  const mayEnter = can('marks', 'enter') || can('marks', 'update');

  const examId = data.exams.some((e) => String(e.id) === examChoice)
    ? examChoice
    : String(data.exams[0]?.id ?? '');
  const exam = data.exams.find((e) => String(e.id) === examId);
  const isPublished = exam?.status === 'published';

  // The classes and subjects offered are the exam's own papers, not every class
  // in the institution: a subject with no scheduled paper has no full marks to
  // enter against.
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

  const classPapers = useMemo(
    () => schedules.filter((s) => String(s.academic_class) === classId),
    [schedules, classId],
  );
  const paper = classPapers.find((s) => String(s.subject) === subjectChoice) ?? classPapers[0];
  const subjectId = paper ? String(paper.subject) : '';

  const load = useCallback(async () => {
    if (!examId || !classId || !subjectId || !exam) {
      setEnrolments([]);
      setRows(new Map());
      return;
    }
    setLoading(true);
    setLoadError(null);
    setSaved(null);
    try {
      const [enrolmentRows, markRows] = await Promise.all([
        apiClient.listAll<Enrolment>(
          '/enrolments/',
          `?session=${exam.session}&academic_class=${classId}&is_active=true&ordering=roll`,
        ),
        apiClient.listAll<Mark>('/marks/', `?exam=${examId}&subject=${subjectId}`),
      ]);
      setEnrolments(enrolmentRows);
      const byEnrolment = new Map(markRows.map((m) => [m.enrolment, m]));
      setRows(
        new Map(
          enrolmentRows.map((e) => {
            const mark = byEnrolment.get(e.id);
            return [
              e.id,
              {
                obtained: marksInputValue(mark?.obtained),
                practical: marksInputValue(mark?.practical_obtained),
                absent: mark?.is_absent ?? false,
              },
            ];
          }),
        ),
      );
    } catch (err) {
      setEnrolments([]);
      setLoadError(apiErrorText(err, t, t('Could not load the marks grid.')));
    } finally {
      setLoading(false);
    }
  }, [examId, classId, subjectId, exam, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const fullMarks = paper ? Number(paper.full_marks) : 100;
  const hasPractical = useMemo(() => {
    const subject = data.subjectsFor(classId).find((s) => String(s.id) === subjectId);
    return Boolean(subject?.has_practical);
  }, [data, classId, subjectId]);

  useEffect(() => {
    if (classId) data.loadSubjects(classId);
  }, [classId, data]);

  const setRow = (enrolmentId: number, patch: Partial<RowDraft>) => {
    setRows((prev) => {
      const next = new Map(prev);
      next.set(enrolmentId, { ...(next.get(enrolmentId) ?? { obtained: '', practical: '', absent: false }), ...patch });
      return next;
    });
  };

  /** Enter and the arrows walk the column, exactly as in the register. */
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>, index: number) => {
    if (event.key !== 'Enter' && event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    const delta = event.key === 'ArrowUp' ? -1 : 1;
    const target = enrolments[index + delta];
    if (target) inputRefs.current.get(target.id)?.focus();
  };

  const save = async () => {
    if (!exam || !subjectId) return;
    setSaving(true);
    setSaveError(null);
    setSaved(null);
    const payload: MarkRowInput[] = enrolments.map((e) => {
      const row = rows.get(e.id) ?? { obtained: '', practical: '', absent: false };
      return {
        enrolment: e.id,
        obtained: row.absent || row.obtained === '' ? null : row.obtained,
        practical_obtained: row.absent || row.practical === '' ? null : row.practical,
        is_absent: row.absent,
      };
    });
    try {
      const result = await apiClient.saveMarks(exam.id, Number(subjectId), payload);
      setSaved(
        `${t('Saved')} — ${result.created} ${t('new')}, ${result.updated} ${t('changed')}, ${result.unchanged} ${t('unchanged')}`,
      );
      await load();
    } catch (err) {
      setSaveError(apiErrorText(err, t, t('Could not save these marks.')));
    } finally {
      setSaving(false);
    }
  };

  const entered = enrolments.filter((e) => {
    const row = rows.get(e.id);
    return row && (row.absent || row.obtained !== '');
  }).length;

  const overFull = enrolments.some((e) => {
    const row = rows.get(e.id);
    if (!row || row.absent || row.obtained === '') return false;
    return Number(row.obtained) > fullMarks;
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
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
          <select
            value={classId}
            onChange={(e) => {
              setClassChoice(e.target.value);
              setSubjectChoice('');
            }}
            className={selectCls}
          >
            {paperClasses.length === 0 && <option value="">{t('No papers scheduled yet.')}</option>}
            {paperClasses.map((c) => (
              <option key={c.id} value={c.id}>
                {classLabel(c)}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Subject')}</span>
          <select
            value={subjectId}
            onChange={(e) => setSubjectChoice(e.target.value)}
            className={selectCls}
          >
            {classPapers.length === 0 && <option value="">{t('No papers scheduled yet.')}</option>}
            {classPapers.map((s) => (
              <option key={s.id} value={s.subject}>
                {s.subject_name || subjectLabel(data.subjectsFor(classId).find((x) => x.id === s.subject))}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loadError && <FormError message={loadError} />}
      {saveError && <FormError message={saveError} />}
      {saved && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {saved}
        </div>
      )}

      {isPublished && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {t('Results are published, so marks can no longer be changed.')}
        </div>
      )}

      {!mayEnter && (
        <p className="text-sm text-gray-500">{t('You can read these marks but not change them.')}</p>
      )}

      {paper && (
        <p className="text-sm text-gray-600">
          {`${t('Full marks')}: ${Number(paper.full_marks)} · ${t('Pass marks')}: ${Number(paper.pass_marks)} · ${entered} / ${enrolments.length} ${t('entered')}`}
        </p>
      )}

      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {!loading && enrolments.length === 0 && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('No students are enrolled in this class.')}
        </div>
      )}

      {enrolments.length > 0 && (
        <ul className="divide-y divide-gray-100 rounded-xl border border-gray-100 bg-white shadow-sm">
          {enrolments.map((enrolment, index) => {
            const row = rows.get(enrolment.id) ?? { obtained: '', practical: '', absent: false };
            const tooHigh = !row.absent && row.obtained !== '' && Number(row.obtained) > fullMarks;
            return (
              <li key={enrolment.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-gray-900">
                    {enrolment.student_name}
                  </span>
                  <span className="block text-xs text-gray-400">
                    {enrolment.roll ?? enrolment.admission_number}
                  </span>
                </span>

                <input
                  ref={(el) => {
                    if (el) inputRefs.current.set(enrolment.id, el);
                    else inputRefs.current.delete(enrolment.id);
                  }}
                  // The phone's numeric keypad, not its alphabet (§7a).
                  inputMode="numeric"
                  value={row.absent ? '' : row.obtained}
                  disabled={!mayEnter || isPublished || row.absent}
                  placeholder={row.absent ? t('Absent') : String(fullMarks)}
                  onChange={(e) => setRow(enrolment.id, { obtained: e.target.value.replace(/[^\d.]/g, '') })}
                  onKeyDown={(e) => onKeyDown(e, index)}
                  aria-label={`${enrolment.student_name} ${t('Marks')}`}
                  className={`h-11 w-20 rounded-lg border px-2 text-center text-base text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 ${
                    tooHigh ? 'border-red-400 bg-red-50' : 'border-gray-200'
                  }`}
                />

                {hasPractical && (
                  <input
                    inputMode="numeric"
                    value={row.absent ? '' : row.practical}
                    disabled={!mayEnter || isPublished || row.absent}
                    placeholder={t('Practical')}
                    onChange={(e) => setRow(enrolment.id, { practical: e.target.value.replace(/[^\d.]/g, '') })}
                    aria-label={`${enrolment.student_name} ${t('Practical')}`}
                    className="h-11 w-20 rounded-lg border border-gray-200 px-2 text-center text-base text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
                  />
                )}

                {/* Absent wins over any number typed beside it — the server
                    normalises the same way, so the tick means one thing. */}
                <button
                  type="button"
                  disabled={!mayEnter || isPublished}
                  onClick={() => setRow(enrolment.id, { absent: !row.absent })}
                  aria-pressed={row.absent}
                  className={`h-11 rounded-lg border px-3 text-sm font-medium disabled:opacity-40 ${
                    row.absent
                      ? 'border-transparent bg-red-50 text-red-700'
                      : 'border-gray-200 bg-white text-gray-500'
                  }`}
                >
                  {t('Absent')}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {enrolments.length > 0 && mayEnter && !isPublished && (
        <div className="sticky bottom-0 z-30 -mx-4 border-t border-gray-200 bg-white/95 px-4 pb-[env(safe-area-inset-bottom)] pt-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
          <div className="flex items-center justify-between gap-3 pb-3">
            <span className="text-sm text-gray-600">
              {overFull ? t('Some marks are above the full marks.') : `${entered} / ${enrolments.length}`}
            </span>
            <span className="flex gap-2">
              <button type="button" onClick={() => void load()} className={btnSecondary} disabled={saving}>
                {t('Reset')}
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving || overFull}
                className={btnPrimary}
              >
                {saving ? t('Saving…') : t('Save')}
              </button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
