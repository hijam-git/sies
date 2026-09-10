import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  AcademicClass,
  AttendanceStatus,
  Period,
  PeriodRoster,
  Section,
  SkippedCell,
  Subject,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, selectCls } from '../common/styles';
import { todayInDhaka } from '../../lib/timezone';
import { STATUSES, studentName } from './shared';

/**
 * Class (period) attendance — the second of the two paths (`docs/08` D7).
 *
 * The roster comes back **defaulted to present**, with anything already
 * recorded winning over the default, because a correction screen that resets
 * thirty students to present quietly destroys the data it was opened to fix.
 * So the teacher marks the absences and submits; the common case is a handful
 * of taps.
 *
 * The attendance window is the server's rule, not this screen's: `is_markable`
 * and its reason arrive with the roster and the save is refused again inside
 * the transaction. Re-deriving "period ended more than N minutes ago" here
 * would be a second copy of a rule an institution can change in its settings.
 */

interface Props {
  classes: AcademicClass[];
  sections: Section[];
  periods: Period[];
  subjects: Subject[];
  onSectionsNeeded: (classId: string) => void;
  /** Prefilled by the teacher's day board — the period they just tapped. */
  initial?: { academicClass: string; section: string; period: string; subject: string } | null;
}

export default function ClassAttendanceTab({
  classes,
  sections,
  periods,
  subjects,
  onSectionsNeeded,
  initial = null,
}: Props) {
  const { t, lang } = useT();
  const { can } = usePermissions();

  const [classChoice, setClassChoice] = useState(initial?.academicClass ?? '');
  const [sectionId, setSectionId] = useState(initial?.section ?? '');
  const [periodChoice, setPeriodChoice] = useState(initial?.period ?? '');
  const [subjectId, setSubjectId] = useState(initial?.subject ?? '');
  const [date, setDate] = useState(todayInDhaka());

  const [roster, setRoster] = useState<PeriodRoster | null>(null);
  const [statuses, setStatuses] = useState<Map<number, AttendanceStatus>>(new Map());
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState<number | null>(null);
  const [skipped, setSkipped] = useState<SkippedCell[]>([]);
  const [saving, setSaving] = useState(false);

  const mayTake = can('attendance', 'take') || can('attendance', 'update');

  const classId = classes.some((c) => String(c.id) === classChoice)
    ? classChoice
    : String(classes[0]?.id ?? '');

  const teachingPeriods = useMemo(() => periods.filter((p) => !p.is_break), [periods]);
  const periodId = teachingPeriods.some((p) => String(p.id) === periodChoice)
    ? periodChoice
    : String(teachingPeriods[0]?.id ?? '');

  const classSections = useMemo(
    () => sections.filter((s) => String(s.academic_class) === classId),
    [sections, classId],
  );
  const classSubjects = useMemo(
    () => subjects.filter((s) => String(s.academic_class) === classId),
    [subjects, classId],
  );

  useEffect(() => {
    if (classId) onSectionsNeeded(classId);
  }, [classId, onSectionsNeeded]);

  const load = useCallback(async () => {
    if (!classId || !periodId) {
      setRoster(null);
      return;
    }
    setLoading(true);
    setLoadError(null);
    setSaved(null);
    setSkipped([]);
    try {
      const data = await apiClient.getPeriodRoster({
        academicClass: Number(classId),
        section: sectionId ? Number(sectionId) : null,
        period: Number(periodId),
        date,
      });
      setRoster(data);
      setStatuses(new Map(data.students.map((s) => [s.student, s.status])));
    } catch (err) {
      setRoster(null);
      setLoadError(apiErrorText(err, t, t('Could not load the roster.')));
    } finally {
      setLoading(false);
    }
  }, [classId, sectionId, periodId, date, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const submit = async () => {
    if (!roster) return;
    setSaving(true);
    setSaveError(null);
    setSkipped([]);
    try {
      const result = await apiClient.savePeriodAttendance({
        academicClass: roster.class,
        section: roster.section,
        subject: subjectId ? Number(subjectId) : null,
        period: roster.period,
        date: roster.date,
        cells: roster.students.map((s) => ({
          student: s.student,
          date: roster.date,
          status: statuses.get(s.student) ?? 'present',
        })),
      });
      setSaved(result.saved);
      setSkipped(result.skipped);
      await load();
      setSaved(result.saved);
      setSkipped(result.skipped);
    } catch (err) {
      setSaveError(apiErrorText(err, t, t('Could not save attendance.')));
    } finally {
      setSaving(false);
    }
  };

  const markAll = (status: AttendanceStatus) => {
    if (!roster) return;
    setStatuses(new Map(roster.students.map((s) => [s.student, status])));
  };

  const presentCount = roster
    ? roster.students.filter((s) => {
        const v = statuses.get(s.student);
        return v === 'present' || v === 'late';
      }).length
    : 0;

  const blockedReason =
    roster && !roster.is_markable ? (lang === 'bn' ? roster.reason_text_bn : roster.reason_text) : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Class')}</span>
          <select
            value={classId}
            onChange={(e) => {
              setClassChoice(e.target.value);
              setSectionId('');
              setSubjectId('');
            }}
            className={selectCls}
          >
            {classes.length === 0 && <option value="">{t('No classes are assigned to you.')}</option>}
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name_bn || c.name}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Section')}</span>
          <select value={sectionId} onChange={(e) => setSectionId(e.target.value)} className={selectCls}>
            <option value="">{t('Whole class')}</option>
            {classSections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name_bn || s.name}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Period')}</span>
          <select value={periodId} onChange={(e) => setPeriodChoice(e.target.value)} className={selectCls}>
            {teachingPeriods.length === 0 && <option value="">{t('No periods are set up yet.')}</option>}
            {teachingPeriods.map((p) => (
              <option key={p.id} value={p.id}>
                {`${p.name_bn || p.name} · ${p.start_time.slice(0, 5)}`}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Date')}</span>
          <input
            type="date"
            value={date}
            max={todayInDhaka()}
            onChange={(e) => e.target.value && setDate(e.target.value)}
            className="min-h-[44px] w-full rounded-lg border border-gray-200 bg-white px-3 text-base text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </label>
      </div>

      {classSubjects.length > 0 && (
        <label className="block sm:max-w-xs">
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Subject')}</span>
          <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)} className={selectCls}>
            <option value="">{t('Not recorded')}</option>
            {classSubjects.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name_bn || s.name}
              </option>
            ))}
          </select>
        </label>
      )}

      {loadError && <FormError message={loadError} />}
      {saveError && <FormError message={saveError} />}

      {blockedReason && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {blockedReason}
        </div>
      )}

      {saved !== null && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {`${t('Saved')}: ${saved}`}
        </div>
      )}

      {skipped.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-medium">{`${t('Not saved')}: ${skipped.length}`}</p>
          <ul className="mt-1 space-y-0.5">
            {skipped.map((row) => (
              <li key={`${row.student}|${row.date}`}>
                {`${row.student} · ${row.date} — ${lang === 'bn' ? row.reason_text_bn : row.reason_text}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {roster && roster.students.length === 0 && !loading && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('No students are enrolled in this class.')}
        </div>
      )}

      {roster && roster.students.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm text-gray-600">
              {`${t('Present')}: ${presentCount} / ${roster.students.length}`}
            </span>
            <span className="flex gap-2">
              <button
                type="button"
                disabled={!mayTake || !roster.is_markable}
                onClick={() => markAll('present')}
                className={btnSecondary}
              >
                {t('All present')}
              </button>
              <button
                type="button"
                disabled={!mayTake || !roster.is_markable}
                onClick={() => markAll('absent')}
                className={btnSecondary}
              >
                {t('All absent')}
              </button>
            </span>
          </div>

          <ul className="divide-y divide-gray-100 rounded-xl border border-gray-100 bg-white shadow-sm">
            {roster.students.map((student) => {
              const current = statuses.get(student.student) ?? 'present';
              return (
                <li key={student.student} className="px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-gray-900">
                        {studentName(student)}
                      </span>
                      <span className="block text-xs text-gray-400">
                        {student.roll ?? student.student_code}
                        {student.is_taken ? ` · ${t('Already recorded')}` : ''}
                      </span>
                    </span>
                    <span className="flex shrink-0 gap-1">
                      {STATUSES.slice(0, 4).map((s) => (
                        <button
                          key={s.value}
                          type="button"
                          disabled={!mayTake || !roster.is_markable}
                          onClick={() =>
                            setStatuses((prev) => new Map(prev).set(student.student, s.value))
                          }
                          aria-pressed={current === s.value}
                          aria-label={t(s.label)}
                          className={`h-11 w-11 rounded-lg border text-sm font-semibold disabled:opacity-40 ${
                            current === s.value
                              ? `${s.cell} border-transparent`
                              : 'border-gray-200 bg-white text-gray-400'
                          }`}
                        >
                          {s.key}
                        </button>
                      ))}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="sticky bottom-0 z-30 -mx-4 border-t border-gray-200 bg-white/95 px-4 pb-[env(safe-area-inset-bottom)] pt-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
            <div className="pb-3">
              <button
                type="button"
                onClick={() => void submit()}
                disabled={saving || !mayTake || !roster.is_markable}
                className={`${btnPrimary} w-full justify-center`}
              >
                {saving ? t('Saving…') : t('Submit attendance')}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
