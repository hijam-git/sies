import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass, Session, SubjectAssignment, Subject, Teacher } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import Field, { FormError } from '../common/Field';
import { selectCls } from '../common/styles';

/**
 * Assignments — who teaches what, and therefore what they can reach
 * (`docs/08` D6).
 *
 * This screen is not a directory. With the institution's
 * `restrict_teachers_to_assigned_classes` setting on, these rows are the access
 * grant: a teacher's attendance register, their student list and their marks
 * entry are all narrowed to the classes named here, and a class nobody assigned
 * them answers 404 rather than an error they can argue with. The line of copy at
 * the top says exactly that, because an admin who reads this as a label will
 * wonder later why a teacher cannot open their own register.
 *
 * Session first, then one class at a time. An institution sets these once a
 * year, class by class, holding a printed list — and a flat table of four
 * hundred subject rows is not the shape of that job.
 */

export default function AssignmentsTab({
  sessions,
  classes,
  teachers,
}: {
  sessions: Session[];
  classes: AcademicClass[];
  teachers: Teacher[];
}) {
  const { t } = useT();
  const { can, canView } = usePermissions();

  // The pickers hold the CHOICE; the values in use fall back to the current
  // session and its first class. Derived rather than seeded from an effect,
  // which would render once with nothing chosen and again with the default.
  const [sessionChoice, setSessionChoice] = useState('');
  const [classChoice, setClassChoice] = useState('');
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [assignments, setAssignments] = useState<SubjectAssignment[]>([]);
  const [classRow, setClassRow] = useState<AcademicClass | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** The row currently being written, so only its own select is disabled and
   *  the rest of the list stays usable. */
  const [busySubject, setBusySubject] = useState<number | null>(null);
  const [busyClassTeacher, setBusyClassTeacher] = useState(false);

  // The assignment IS the academic frame, so it is gated on `academics` and not
  // on `teachers`: whoever may edit the classes may say who teaches them.
  const mayEdit = can('academics', 'update');
  const mayView = canView('academics');

  const sessionId =
    sessionChoice || String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? '');

  const sessionClasses = useMemo(
    () => classes.filter((c) => String(c.session) === sessionId),
    [classes, sessionId],
  );

  const classId = sessionClasses.some((c) => String(c.id) === classChoice)
    ? classChoice
    : String(sessionClasses[0]?.id ?? '');

  const load = useCallback(async () => {
    if (!sessionId || !classId) {
      setSubjects([]);
      setAssignments([]);
      setClassRow(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [subjectRows, assignmentRows, classDetail] = await Promise.all([
        apiClient.listAll<Subject>('/subjects/', `?academic_class=${classId}&is_active=true`),
        apiClient.listAll<SubjectAssignment>(
          '/subject-assignments/',
          `?session=${sessionId}&academic_class=${classId}&is_active=true`,
        ),
        apiClient.retrieve<AcademicClass>('/classes/', Number(classId)),
      ]);
      setSubjects(subjectRows);
      setAssignments(assignmentRows);
      setClassRow(classDetail);
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not load the assignments.')));
    } finally {
      setLoading(false);
    }
  }, [sessionId, classId, t]);

  // Deferred by a tick rather than called from the effect body: `load` sets
  // state synchronously, which during an effect cascades a render before the
  // first paint. The same shape the other list screens use.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const assignedTo = (subjectId: number) =>
    assignments.find((a) => a.subject === subjectId) ?? null;

  const setSubjectTeacher = async (subject: Subject, teacherId: string) => {
    setBusySubject(subject.id);
    setError(null);
    const existing = assignedTo(subject.id);
    try {
      if (!teacherId) {
        // Removing the row and not blanking the teacher: an assignment with no
        // teacher is an access grant to nobody, which the model has no way to
        // express and the D6 scope query would read as a class with a hole.
        if (existing) await apiClient.destroy('/subject-assignments/', existing.id);
      } else if (existing) {
        await apiClient.patch<SubjectAssignment>('/subject-assignments/', existing.id, {
          teacher: Number(teacherId),
        });
      } else {
        await apiClient.create<SubjectAssignment>('/subject-assignments/', {
          session: Number(sessionId),
          academic_class: Number(classId),
          subject: subject.id,
          teacher: Number(teacherId),
          section: null,
          is_active: true,
        });
      }
      await load();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not save this assignment.')));
    } finally {
      setBusySubject(null);
    }
  };

  const setClassTeacher = async (teacherId: string) => {
    if (!classRow) return;
    setBusyClassTeacher(true);
    setError(null);
    try {
      await apiClient.patch<AcademicClass>('/classes/', classRow.id, {
        class_teacher: teacherId ? Number(teacherId) : null,
      });
      await load();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not save the class teacher.')));
    } finally {
      setBusyClassTeacher(false);
    }
  };

  if (!mayView) {
    return (
      <p className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
        {t('You do not have permission to do this.')}
      </p>
    );
  }

  const assignedCount = subjects.filter((s) => assignedTo(s.id)).length;

  return (
    <div className="space-y-4">
      <p className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm leading-relaxed text-blue-900">
        {t('An assignment is what a teacher can reach: attendance and marks are limited to the classes named here.')}
      </p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t('Session')}>
          <select value={sessionId} onChange={(e) => setSessionChoice(e.target.value)} className={selectCls}>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('Class')}>
          <select value={classId} onChange={(e) => setClassChoice(e.target.value)} className={selectCls}>
            <option value="">{t('Choose a class')}</option>
            {sessionClasses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name_bn || c.name}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {error && <FormError message={error} />}

      {!classId ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Choose a class to set its teachers.')}
        </div>
      ) : (
        <div className="space-y-4">
          <section className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
            <h3 className="mb-1 text-sm font-semibold text-gray-900">{t('Class teacher')}</h3>
            <p className="mb-3 text-xs text-gray-500">
              {t('Owns the daily register for this class and may correct a cell somebody else filled in.')}
            </p>
            <select
              value={classRow?.class_teacher === null || classRow === null ? '' : String(classRow.class_teacher)}
              onChange={(e) => void setClassTeacher(e.target.value)}
              disabled={!mayEdit || busyClassTeacher}
              aria-label={t('Class teacher')}
              className={selectCls}
            >
              <option value="">{t('Not assigned')}</option>
              {teachers.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name_bn || x.name}
                </option>
              ))}
            </select>
          </section>

          <section className="rounded-xl border border-gray-100 bg-white shadow-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-gray-100 px-4 py-3">
              <h3 className="text-sm font-semibold text-gray-900">{t('Subject teachers')}</h3>
              <span className="text-xs text-gray-500">
                {`${assignedCount} / ${subjects.length} ${t('assigned')}`}
              </span>
            </div>

            {subjects.length === 0 ? (
              <p className="p-8 text-center text-sm text-gray-500">
                {loading ? t('Loading…') : t('This class has no subjects yet.')}
              </p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {subjects.map((s) => {
                  const current = assignedTo(s.id);
                  return (
                    // Stacked at 360px, side by side from sm — a label and a
                    // select sharing a phone row leaves the select unreadable.
                    <li key={s.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:gap-4">
                      <span className="min-w-0 sm:w-1/3">
                        <span className="block text-sm font-medium text-gray-900">{s.name_bn || s.name}</span>
                        {s.code && <span className="block font-mono text-xs text-gray-400">{s.code}</span>}
                      </span>
                      <span className="min-w-0 flex-1">
                        <select
                          value={current ? String(current.teacher) : ''}
                          onChange={(e) => void setSubjectTeacher(s, e.target.value)}
                          disabled={!mayEdit || busySubject === s.id}
                          aria-label={`${t('Teacher')} — ${s.name_bn || s.name}`}
                          className={selectCls}
                        >
                          <option value="">{t('Not assigned')}</option>
                          {teachers.map((x) => (
                            <option key={x.id} value={x.id}>
                              {x.name_bn || x.name}
                            </option>
                          ))}
                        </select>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
