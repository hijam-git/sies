import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Exam, ExamClass, ExamSchedule, ExamType } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import {
  EXAM_STATUS_CLASS,
  EXAM_STATUS_LABEL,
  EXAM_TYPES,
  classLabel,
  examLabel,
  subjectLabel,
} from './shared';
import type { ExamsData } from './shared';

/**
 * Exams — the event, the classes that sit it, and the paper-by-paper schedule.
 *
 * `status` is deliberately not editable here. The only route to `published` is
 * `POST /exams/<id>/publish/`, gated on `exams.publish`, because publishing is
 * the moment results become visible to students (`docs/02` §2.1). A status
 * dropdown would hand that decision to anyone holding `exams.update`.
 *
 * There are no delete buttons either, and that is the API's shape rather than
 * an omission: the catalogue has no `exams.delete` action, so the backend
 * refuses a DELETE from everybody. An exam that should not have existed is
 * edited or left alone.
 */

interface ExamDraft {
  id: number | null;
  session: string;
  stream: string;
  name: string;
  name_bn: string;
  exam_type: ExamType;
  starts_on: string;
  ends_on: string;
}

interface ScheduleDraft {
  id: number | null;
  academic_class: string;
  subject: string;
  date: string;
  start_time: string;
  end_time: string;
  full_marks: string;
  pass_marks: string;
  room: string;
  invigilator: string;
}

export default function ExamsTab({ data }: { data: ExamsData }) {
  const { t } = useT();
  const { can } = usePermissions();

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [examClasses, setExamClasses] = useState<ExamClass[]>([]);
  const [schedules, setSchedules] = useState<ExamSchedule[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [examDraft, setExamDraft] = useState<ExamDraft | null>(null);
  const [scheduleDraft, setScheduleDraft] = useState<ScheduleDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('exams', 'create');
  const mayUpdate = can('exams', 'update');

  const selected = data.exams.find((e) => e.id === selectedId) ?? null;
  const isPublished = selected?.status === 'published';

  const loadDetail = useCallback(async (examId: number) => {
    setLoadError(null);
    try {
      const [classRows, scheduleRows] = await Promise.all([
        apiClient.listAll<ExamClass>('/exam-classes/', `?exam=${examId}`),
        apiClient.listAll<ExamSchedule>('/exam-schedules/', `?exam=${examId}&ordering=date`),
      ]);
      setExamClasses(classRows);
      setSchedules(scheduleRows);
    } catch (err) {
      setExamClasses([]);
      setSchedules([]);
      setLoadError(apiErrorText(err, t, t('Could not load this exam.')));
    }
  }, [t]);

  // Deferred a tick, as everywhere else in this dashboard: clearing and
  // fetching both set state, and doing that in an effect body cascades a render
  // before anything is painted.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (selectedId === null) {
        setExamClasses([]);
        setSchedules([]);
        return;
      }
      void loadDetail(selectedId);
    }, 0);
    return () => clearTimeout(timer);
  }, [selectedId, loadDetail]);

  /** The classes sitting this exam, as ids, for the schedule's class picker. */
  const sittingClassIds = useMemo(
    () => new Set(examClasses.map((row) => String(row.academic_class))),
    [examClasses],
  );

  useEffect(() => {
    for (const id of sittingClassIds) data.loadSubjects(id);
  }, [sittingClassIds, data]);

  // ── Exam create / edit ──────────────────────────────────────────────────

  const openExam = (exam: Exam | null) => {
    const currentSession = data.sessions.find((s) => s.is_current) ?? data.sessions[0];
    setExamDraft({
      id: exam?.id ?? null,
      session: String(exam?.session ?? currentSession?.id ?? ''),
      stream: exam?.stream ? String(exam.stream) : '',
      name: exam?.name ?? '',
      name_bn: exam?.name_bn ?? '',
      exam_type: exam?.exam_type ?? 'half_yearly',
      starts_on: exam?.starts_on ?? '',
      ends_on: exam?.ends_on ?? '',
    });
    setFormError(null);
    setFieldErrors({});
  };

  const saveExam = async () => {
    if (!examDraft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      session: Number(examDraft.session),
      stream: examDraft.stream ? Number(examDraft.stream) : null,
      name: examDraft.name.trim(),
      name_bn: examDraft.name_bn.trim(),
      exam_type: examDraft.exam_type,
      starts_on: examDraft.starts_on,
      ends_on: examDraft.ends_on,
    };
    try {
      if (examDraft.id !== null) await apiClient.patch<Exam>('/exams/', examDraft.id, body);
      else {
        const created = await apiClient.create<Exam>('/exams/', body);
        setSelectedId(created.id);
      }
      setExamDraft(null);
      await data.reloadExams();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this exam.')));
    } finally {
      setSaving(false);
    }
  };

  // ── Which classes sit it ────────────────────────────────────────────────

  const addClass = async (classId: string) => {
    if (!selected || !classId) return;
    setFormError(null);
    try {
      await apiClient.create<ExamClass>('/exam-classes/', {
        exam: selected.id,
        academic_class: Number(classId),
      });
      await loadDetail(selected.id);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not add this class to the exam.')));
    }
  };

  // ── The schedule ────────────────────────────────────────────────────────

  const openSchedule = (row: ExamSchedule | null) => {
    const firstClass = examClasses[0];
    setScheduleDraft({
      id: row?.id ?? null,
      academic_class: String(row?.academic_class ?? firstClass?.academic_class ?? ''),
      subject: row ? String(row.subject) : '',
      date: row?.date ?? selected?.starts_on ?? '',
      start_time: row?.start_time?.slice(0, 5) ?? '',
      end_time: row?.end_time?.slice(0, 5) ?? '',
      full_marks: row ? String(Number(row.full_marks)) : '',
      pass_marks: row ? String(Number(row.pass_marks)) : '',
      room: row?.room ?? '',
      invigilator: row?.invigilator ? String(row.invigilator) : '',
    });
    setFormError(null);
    setFieldErrors({});
  };

  const saveSchedule = async () => {
    if (!scheduleDraft || !selected) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      exam: selected.id,
      academic_class: Number(scheduleDraft.academic_class),
      subject: Number(scheduleDraft.subject),
      date: scheduleDraft.date,
      start_time: scheduleDraft.start_time || null,
      end_time: scheduleDraft.end_time || null,
      room: scheduleDraft.room.trim(),
      invigilator: scheduleDraft.invigilator ? Number(scheduleDraft.invigilator) : null,
    };
    // Left out entirely when blank, so the server copies the subject's own
    // full and pass marks — the common case, and one less thing to type on a
    // list of twelve papers.
    if (scheduleDraft.full_marks) body.full_marks = scheduleDraft.full_marks;
    if (scheduleDraft.pass_marks) body.pass_marks = scheduleDraft.pass_marks;

    try {
      if (scheduleDraft.id !== null)
        await apiClient.patch<ExamSchedule>('/exam-schedules/', scheduleDraft.id, body);
      else await apiClient.create<ExamSchedule>('/exam-schedules/', body);
      setScheduleDraft(null);
      await loadDetail(selected.id);
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this paper.')));
    } finally {
      setSaving(false);
    }
  };

  const scheduleSubjects = scheduleDraft ? data.subjectsFor(scheduleDraft.academic_class) : [];

  const examColumns: Column<Exam>[] = [
    {
      key: 'name',
      label: t('Name'),
      primary: true,
      render: (row) => examLabel(row),
    },
    {
      key: 'type',
      label: t('Type'),
      render: (row) => t(EXAM_TYPES.find((x) => x.value === row.exam_type)?.label ?? row.exam_type),
    },
    { key: 'session', label: t('Session'), render: (row) => row.session_name, hideOnNarrow: true },
    {
      key: 'dates',
      label: t('Dates'),
      render: (row) => `${row.starts_on} → ${row.ends_on}`,
    },
    {
      key: 'status',
      label: t('Status'),
      render: (row) => (
        <span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${EXAM_STATUS_CLASS[row.status]}`}>
          {t(EXAM_STATUS_LABEL[row.status])}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {mayCreate && (
          <button type="button" onClick={() => openExam(null)} className={btnPrimary}>
            {t('New exam')}
          </button>
        )}
      </div>

      {loadError && <FormError message={loadError} />}

      <ResponsiveTable
        columns={examColumns}
        rows={data.exams}
        rowKey={(row) => row.id}
        onRowClick={(row) => setSelectedId(row.id === selectedId ? null : row.id)}
        empty={t('No exams yet.')}
      />

      {selected && (
        <section className="space-y-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-gray-900">{examLabel(selected)}</h2>
            {mayUpdate && !isPublished && (
              <button type="button" onClick={() => openExam(selected)} className={btnSecondary}>
                {t('Edit')}
              </button>
            )}
          </div>

          {isPublished && (
            <p className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
              {t('Results are published. Marks and the schedule can no longer be changed.')}
            </p>
          )}

          {/* ── Which classes sit it ─────────────────────────────────────── */}
          <div>
            <h3 className="mb-2 text-sm font-medium text-gray-700">{t('Classes sitting this exam')}</h3>
            <div className="flex flex-wrap gap-2">
              {examClasses.map((row) => (
                <span
                  key={row.id}
                  className="inline-flex rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-700"
                >
                  {row.class_name}
                </span>
              ))}
              {examClasses.length === 0 && (
                <span className="text-sm text-gray-500">{t('No classes added yet.')}</span>
              )}
            </div>
            {mayCreate && !isPublished && (
              <label className="mt-3 block sm:max-w-xs">
                <span className="mb-1 block text-sm font-medium text-gray-700">{t('Add a class')}</span>
                <select
                  value=""
                  onChange={(e) => void addClass(e.target.value)}
                  className={selectCls}
                >
                  <option value="">{t('Choose a class')}</option>
                  {data.classes
                    .filter((c) => !sittingClassIds.has(String(c.id)))
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {classLabel(c)}
                      </option>
                    ))}
                </select>
              </label>
            )}
          </div>

          {/* ── The schedule ─────────────────────────────────────────────── */}
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium text-gray-700">{t('Schedule')}</h3>
              {mayCreate && !isPublished && examClasses.length > 0 && (
                <button type="button" onClick={() => openSchedule(null)} className={btnSecondary}>
                  {t('Add a paper')}
                </button>
              )}
            </div>

            <ResponsiveTable
              columns={[
                { key: 'subject', label: t('Subject'), primary: true, render: (row: ExamSchedule) => row.subject_name },
                { key: 'class', label: t('Class'), render: (row: ExamSchedule) => row.class_name },
                { key: 'date', label: t('Date'), render: (row: ExamSchedule) => row.date },
                {
                  key: 'time',
                  label: t('Time'),
                  render: (row: ExamSchedule) =>
                    row.start_time ? `${row.start_time.slice(0, 5)}–${(row.end_time ?? '').slice(0, 5)}` : '—',
                  hideOnNarrow: true,
                },
                {
                  key: 'marks',
                  label: t('Marks'),
                  render: (row: ExamSchedule) => `${Number(row.full_marks)} / ${Number(row.pass_marks)}`,
                },
                { key: 'room', label: t('Room'), render: (row: ExamSchedule) => row.room || '—', hideOnNarrow: true },
                {
                  key: 'edit',
                  label: t('Actions'),
                  action: true,
                  render: (row: ExamSchedule) =>
                    mayUpdate && !isPublished ? (
                      <button
                        type="button"
                        onClick={() => openSchedule(row)}
                        className="text-sm font-medium text-blue-700 hover:underline"
                      >
                        {t('Edit')}
                      </button>
                    ) : null,
                },
              ]}
              rows={schedules}
              rowKey={(row) => row.id}
              empty={t('No papers scheduled yet.')}
            />
          </div>
        </section>
      )}

      {/* ── Exam form ───────────────────────────────────────────────────── */}
      <BaseModal
        isOpen={examDraft !== null}
        onClose={() => setExamDraft(null)}
        title={examDraft?.id ? t('Edit exam') : t('New exam')}
        maxWidth="lg"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setExamDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void saveExam()}
              disabled={saving || !examDraft?.name.trim() || !examDraft?.starts_on || !examDraft?.ends_on}
              className={`${btnPrimary} flex-1`}
            >
              {saving ? t('Saving…') : t('Save')}
            </button>
          </div>
        }
      >
        {examDraft && (
          <div className="space-y-4">
            <FormError message={formError} />
            <FieldGrid>
              <Field label={t('Name')} error={fieldErrors.name} required>
                <input
                  value={examDraft.name}
                  onChange={(e) => setExamDraft({ ...examDraft, name: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Name (Bangla)')} error={fieldErrors.name_bn}>
                <input
                  value={examDraft.name_bn}
                  onChange={(e) => setExamDraft({ ...examDraft, name_bn: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Session')} error={fieldErrors.session} required>
                <select
                  value={examDraft.session}
                  onChange={(e) => setExamDraft({ ...examDraft, session: e.target.value })}
                  className={selectCls}
                >
                  {data.sessions.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Stream')} error={fieldErrors.stream} hint={t('Leave empty for the whole institution.')}>
                <select
                  value={examDraft.stream}
                  onChange={(e) => setExamDraft({ ...examDraft, stream: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('All streams')}</option>
                  {data.streams.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name_bn || s.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Type')} error={fieldErrors.exam_type} required>
                <select
                  value={examDraft.exam_type}
                  onChange={(e) => setExamDraft({ ...examDraft, exam_type: e.target.value as ExamType })}
                  className={selectCls}
                >
                  {EXAM_TYPES.map((x) => (
                    <option key={x.value} value={x.value}>
                      {t(x.label)}
                    </option>
                  ))}
                </select>
              </Field>
              <FieldWide>
                <FieldGrid>
                  <Field label={t('Starts on')} error={fieldErrors.starts_on} required>
                    <input
                      type="date"
                      value={examDraft.starts_on}
                      onChange={(e) => setExamDraft({ ...examDraft, starts_on: e.target.value })}
                      className={inputCls}
                    />
                  </Field>
                  <Field label={t('Ends on')} error={fieldErrors.ends_on} required>
                    <input
                      type="date"
                      value={examDraft.ends_on}
                      onChange={(e) => setExamDraft({ ...examDraft, ends_on: e.target.value })}
                      className={inputCls}
                    />
                  </Field>
                </FieldGrid>
              </FieldWide>
            </FieldGrid>
          </div>
        )}
      </BaseModal>

      {/* ── Paper form ──────────────────────────────────────────────────── */}
      <BaseModal
        isOpen={scheduleDraft !== null}
        onClose={() => setScheduleDraft(null)}
        title={scheduleDraft?.id ? t('Edit paper') : t('Add a paper')}
        maxWidth="lg"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setScheduleDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void saveSchedule()}
              disabled={saving || !scheduleDraft?.subject || !scheduleDraft?.date}
              className={`${btnPrimary} flex-1`}
            >
              {saving ? t('Saving…') : t('Save')}
            </button>
          </div>
        }
      >
        {scheduleDraft && (
          <div className="space-y-4">
            <FormError message={formError} />
            <FieldGrid>
              <Field label={t('Class')} error={fieldErrors.academic_class} required>
                <select
                  value={scheduleDraft.academic_class}
                  onChange={(e) =>
                    setScheduleDraft({ ...scheduleDraft, academic_class: e.target.value, subject: '' })
                  }
                  className={selectCls}
                >
                  {examClasses.map((row) => (
                    <option key={row.id} value={row.academic_class}>
                      {row.class_name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Subject')} error={fieldErrors.subject} required>
                <select
                  value={scheduleDraft.subject}
                  onChange={(e) => setScheduleDraft({ ...scheduleDraft, subject: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Choose a subject')}</option>
                  {scheduleSubjects.map((s) => (
                    <option key={s.id} value={s.id}>
                      {subjectLabel(s)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Date')} error={fieldErrors.date} required>
                <input
                  type="date"
                  value={scheduleDraft.date}
                  onChange={(e) => setScheduleDraft({ ...scheduleDraft, date: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Room')} error={fieldErrors.room}>
                <input
                  value={scheduleDraft.room}
                  onChange={(e) => setScheduleDraft({ ...scheduleDraft, room: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Starts at')} error={fieldErrors.start_time}>
                <input
                  type="time"
                  value={scheduleDraft.start_time}
                  onChange={(e) => setScheduleDraft({ ...scheduleDraft, start_time: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Ends at')} error={fieldErrors.end_time}>
                <input
                  type="time"
                  value={scheduleDraft.end_time}
                  onChange={(e) => setScheduleDraft({ ...scheduleDraft, end_time: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field
                label={t('Full marks')}
                error={fieldErrors.full_marks}
                hint={t('Left empty, the subject’s own marks are used.')}
              >
                <input
                  inputMode="numeric"
                  value={scheduleDraft.full_marks}
                  onChange={(e) => setScheduleDraft({ ...scheduleDraft, full_marks: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Pass marks')} error={fieldErrors.pass_marks}>
                <input
                  inputMode="numeric"
                  value={scheduleDraft.pass_marks}
                  onChange={(e) => setScheduleDraft({ ...scheduleDraft, pass_marks: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <FieldWide>
                <Field label={t('Invigilator')} error={fieldErrors.invigilator}>
                  <select
                    value={scheduleDraft.invigilator}
                    onChange={(e) => setScheduleDraft({ ...scheduleDraft, invigilator: e.target.value })}
                    className={selectCls}
                  >
                    <option value="">{t('Not assigned')}</option>
                    {data.teachers.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.name_bn || x.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </FieldWide>
            </FieldGrid>
          </div>
        )}
      </BaseModal>
    </div>
  );
}
