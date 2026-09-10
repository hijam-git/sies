import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { ClassRoutine, DayOfWeek, Period, Section, Subject } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import Field, { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import Picker from '../common/Picker';
import { preferredClassId, useOwnTeacherId } from '../../lib/defaults';
import PeriodsPanel from './PeriodsPanel';
import MasterRoutine from './MasterRoutine';
import { WEEK_DAYS, classLabel, periodLabel, shortTime, todayWeekIndex } from './shared';
import type { AcademicsData } from './shared';

/**
 * The weekly routine — one class's timetable, seven days by however many
 * periods the bell schedule has.
 *
 * **Two layouts, not one that shrinks.** From `md` up it is the grid the office
 * prints: days across, periods down. Below `md` it is a day picker and that
 * day's periods as a vertical list, for the same reason the attendance register
 * has a single-day mode (`CLAUDE.md` §7a) — seven columns of subject-plus-
 * teacher at 360px is unreadable at any zoom, and one day is what somebody
 * standing in a corridor actually wants.
 *
 * **Clashes are shown while the cell is open, not after Save.** The backend
 * refuses a double-booked teacher with a unique constraint, and an integrity
 * error cannot say *who* is busy *where*. Every routine row for the session is
 * already loaded to draw the grid, so the same answer the server would give is
 * available before the request is made — and the request is still made, because
 * the database is the guarantee and another user may have booked the teacher a
 * second ago.
 */

interface CellDraft {
  day: DayOfWeek;
  period: number;
  /** The existing row being edited, or null for an empty cell. */
  id: number | null;
  subject: string;
  teacher: string;
  room: string;
}

export default function RoutineTab({ data }: { data: AcademicsData }) {
  const { t } = useT();
  const { can } = usePermissions();

  // The pickers hold the user's CHOICE, and the value in use is derived from it
  // (`|| the default`). Storing a default in state instead would mean writing it
  // from an effect on first render — a second render before anything is drawn,
  // and a stale value every time the session list arrives late.
  const [sessionChoice, setSessionChoice] = useState<string>('');
  const [classChoice, setClassChoice] = useState<string>('');
  // Which question is being asked: one class's week, or one day across the
  // whole institution. `MasterRoutine` answers the second two.
  const [scope, setScope] = useState<'class' | 'classes' | 'teachers'>('class');
  const [sectionId, setSectionId] = useState<string>('');
  const [day, setDay] = useState<DayOfWeek>(todayWeekIndex());

  const [periods, setPeriods] = useState<Period[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  /** Every routine row in the session, across every class — the teacher clash
   *  check needs the rows this class cannot see. */
  const [allRoutines, setAllRoutines] = useState<ClassRoutine[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<CellDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('academics', 'create');
  const mayUpdate = can('academics', 'update');
  const mayDelete = can('academics', 'delete');
  const mayEdit = mayCreate || mayUpdate;

  const sessionId =
    sessionChoice ||
    String((data.sessions.find((s) => s.is_current) ?? data.sessions[0])?.id ?? '');

  const sessionClasses = useMemo(
    () => data.classes.filter((c) => String(c.session) === sessionId),
    [data.classes, sessionId],
  );

  // A class chosen under another session is not in this one's list, so it falls
  // back rather than leaving the grid pointed at nothing — and the fallback is
  // the reader's own class when the account resolves to a teacher.
  const ownTeacherId = useOwnTeacherId(data.teachers);
  const classId = sessionClasses.some((c) => String(c.id) === classChoice)
    ? classChoice
    : preferredClassId(sessionClasses, ownTeacherId);

  const loadPeriods = useCallback(
    () =>
      apiClient
        .listAll<Period>('/periods/', '?is_active=true&ordering=order')
        .then(setPeriods)
        .catch(() => setPeriods([])),
    [],
  );

  useEffect(() => {
    void loadPeriods();
  }, [loadPeriods]);

  const load = useCallback(async () => {
    if (!sessionId) {
      setAllRoutines([]);
      setSubjects([]);
      setSections([]);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      // The session's rows are fetched whether or not a class is chosen: they
      // are what the whole-institution views draw, and the clash check needs
      // them anyway. Subjects and sections are per class, so they wait for one.
      const [routines, subjectRows, sectionRows] = await Promise.all([
        apiClient.listAll<ClassRoutine>('/class-routines/', `?session=${sessionId}&is_active=true`),
        classId
          ? apiClient.listAll<Subject>('/subjects/', `?academic_class=${classId}&is_active=true`)
          : Promise.resolve([] as Subject[]),
        classId
          ? apiClient.listAll<Section>('/sections/', `?academic_class=${classId}&is_active=true`)
          : Promise.resolve([] as Section[]),
      ]);
      setAllRoutines(routines);
      setSubjects(subjectRows);
      setSections(sectionRows);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the routine.')));
    } finally {
      setLoading(false);
    }
  }, [sessionId, classId, t]);

  // Deferred by a tick, not called straight from the effect body: `load` sets
  // state synchronously, and doing that during an effect cascades a render
  // before the first paint. The same debounce the other list screens use.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  /** The rows drawn in the grid: this class, and this section if one is chosen.
   *  A section of "" means the class-wide routine, which is what a class with no
   *  sections has. */
  const cells = useMemo(() => {
    const wanted = sectionId ? Number(sectionId) : null;
    const map = new Map<string, ClassRoutine>();
    for (const row of allRoutines) {
      if (String(row.academic_class) !== classId) continue;
      if ((row.section ?? null) !== wanted) continue;
      map.set(`${row.day_of_week}:${row.period}`, row);
    }
    return map;
  }, [allRoutines, classId, sectionId]);

  const teachingPeriods = useMemo(() => periods.filter((p) => !p.is_break), [periods]);

  /**
   * Who else this teacher is already teaching at this hour, if anybody.
   *
   * The same rule the server's unique constraint enforces, applied to the rows
   * already on screen: same session, same day, same period, a different row.
   */
  const clashFor = useCallback(
    (teacherId: string, dayIndex: DayOfWeek, periodId: number, ignoreId: number | null) => {
      if (!teacherId) return null;
      const busy = allRoutines.find(
        (row) =>
          row.id !== ignoreId &&
          String(row.teacher) === teacherId &&
          row.day_of_week === dayIndex &&
          row.period === periodId,
      );
      if (!busy) return null;
      const where = data.classes.find((c) => c.id === busy.academic_class);
      return { teacher: busy.teacher_name, className: where ? classLabel(where) : String(busy.academic_class) };
    },
    [allRoutines, data.classes],
  );

  const openCell = (dayIndex: DayOfWeek, period: Period) => {
    if (!mayEdit) return;
    const existing = cells.get(`${dayIndex}:${period.id}`);
    setDraft({
      day: dayIndex,
      period: period.id,
      id: existing?.id ?? null,
      subject: existing ? String(existing.subject) : '',
      teacher: existing ? String(existing.teacher) : '',
      room: existing?.room ?? '',
    });
    setFormError(null);
    setFieldErrors({});
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      session: Number(sessionId),
      academic_class: Number(classId),
      section: sectionId ? Number(sectionId) : null,
      subject: Number(draft.subject),
      teacher: Number(draft.teacher),
      period: draft.period,
      day_of_week: draft.day,
      room: draft.room.trim(),
      is_active: true,
    };
    try {
      if (draft.id !== null) await apiClient.patch<ClassRoutine>('/class-routines/', draft.id, body);
      else await apiClient.create<ClassRoutine>('/class-routines/', body);
      setDraft(null);
      await load();
    } catch (err) {
      // The backend's own clash message is already a sentence naming the class,
      // so it is shown as it came rather than replaced with a generic one.
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this lesson.')));
    } finally {
      setSaving(false);
    }
  };

  const clearCell = async () => {
    if (!draft?.id) return;
    setSaving(true);
    try {
      await apiClient.destroy('/class-routines/', draft.id);
      setDraft(null);
      await load();
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not clear this lesson.')));
    } finally {
      setSaving(false);
    }
  };

  const liveClash = draft
    ? clashFor(draft.teacher, draft.day, draft.period, draft.id)
    : null;

  const cellContent = (row: ClassRoutine | undefined) =>
    row ? (
      <>
        <span className="block truncate text-sm font-medium text-gray-900">{row.subject_name}</span>
        <span className="block truncate text-xs text-gray-600">{row.teacher_name}</span>
        {row.room && <span className="block truncate text-xs text-gray-400">{row.room}</span>}
      </>
    ) : (
      <span className="text-xs text-gray-300">{mayEdit ? '+' : '—'}</span>
    );

  const chosenClass = data.classes.find((c) => String(c.id) === classId);

  const SCOPES: { key: typeof scope; label: string }[] = [
    { key: 'class', label: 'One class' },
    { key: 'classes', label: 'All classes' },
    { key: 'teachers', label: 'All teachers' },
  ];

  return (
    <div className="space-y-4">
      <div className="scroll-x -mx-1 px-1">
        <div className="flex w-max gap-1">
          {SCOPES.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setScope(s.key)}
              aria-pressed={scope === s.key}
              className={`min-h-[40px] whitespace-nowrap rounded-lg px-3 text-sm font-medium ${
                scope === s.key
                  ? 'bg-gray-900 text-white'
                  : 'border border-gray-200 bg-white text-gray-600'
              }`}
            >
              {t(s.label)}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label={t('Session')}>
          <Picker
            value={sessionId}
            onChange={(v) => {
              setSessionChoice(v);
              setSectionId('');
            }}
            options={data.sessions.map((s) => ({ value: String(s.id), label: s.name }))}
          />
        </Field>
        {/* A class and a section narrow one class's week. The whole-institution
            views are already about every class, so asking there would be a
            control that contradicts the heading above it. */}
        {scope === 'class' && (
          <>
            <Field label={t('Class')}>
              <Picker
                value={classId}
                onChange={(v) => {
                  setClassChoice(v);
                  setSectionId('');
                }}
                options={sessionClasses.map((c) => ({ value: String(c.id), label: classLabel(c) }))}
                emptyLabel={t('Choose a class')}
              />
            </Field>
            <Field label={t('Section')}>
              <Picker
                value={sectionId}
                onChange={setSectionId}
                options={sections.map((s) => ({ value: String(s.id), label: s.name_bn || s.name }))}
                anyLabel={t('Whole class')}
              />
            </Field>
          </>
        )}
      </div>

      {loadError && <FormError message={loadError} />}

      {scope === 'class' && (
        <PeriodsPanel periods={periods} streams={data.streams} onChanged={async () => { await loadPeriods(); await load(); }} />
      )}

      {scope !== 'class' ? (
        <MasterRoutine
          mode={scope}
          day={day}
          onDayChange={setDay}
          routines={allRoutines}
          periods={teachingPeriods}
          classes={sessionClasses}
          // Someone on leave still holds their periods and still shows a clash;
          // someone who has left does not, and their empty row would read as a
          // free teacher to give a class to.
          teachers={data.teachers.filter(
            (x) => x.employment_status === 'active' || x.employment_status === 'on_leave',
          )}
          // A cell is a link into the editable grid for that class, so the one
          // place a lesson can be changed stays the one place.
          onOpenClass={(id) => {
            setClassChoice(String(id));
            setSectionId('');
            setScope('class');
          }}
        />
      ) : teachingPeriods.length === 0 ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Add a period above before building the routine.')}
        </div>
      ) : !classId ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Choose a class to see its week.')}
        </div>
      ) : (
        <>
          {/* ── Phone: one day at a time ─────────────────────────────────── */}
          <div className="md:hidden">
            {/* The day strip scrolls inside itself; the body never scrolls
                sideways (§7a rule 1). */}
            <div className="scroll-x -mx-1 mb-3 px-1">
              <div className="flex w-max gap-1">
                {WEEK_DAYS.map((d) => (
                  <button
                    key={d.value}
                    type="button"
                    onClick={() => setDay(d.value)}
                    aria-pressed={day === d.value}
                    className={`min-h-[44px] whitespace-nowrap rounded-lg px-4 text-sm font-medium ${
                      day === d.value
                        ? 'bg-blue-600 text-white'
                        : 'border border-gray-200 bg-white text-gray-600'
                    }`}
                  >
                    {t(d.label)}
                  </button>
                ))}
              </div>
            </div>

            <ul className="divide-y divide-gray-100 rounded-xl border border-gray-100 bg-white shadow-sm">
              {teachingPeriods.map((p) => {
                const row = cells.get(`${day}:${p.id}`);
                return (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => openCell(day, p)}
                      disabled={!mayEdit}
                      className="flex min-h-[64px] w-full items-center gap-3 px-4 py-3 text-left disabled:cursor-default"
                    >
                      <span className="w-20 shrink-0">
                        <span className="block text-sm font-medium text-gray-900">{periodLabel(p)}</span>
                        <span className="block text-xs text-gray-400">{shortTime(p.start_time)}</span>
                      </span>
                      <span className="min-w-0 flex-1">{cellContent(row)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* ── md and up: the printed grid ──────────────────────────────── */}
          <div className="scroll-x hidden rounded-xl border border-gray-100 bg-white shadow-sm md:block">
            <table className="min-w-full border-collapse">
              <thead>
                <tr>
                  {/* Sticky first column so the period stays readable while the
                      days scroll on a tablet. */}
                  <th className="sticky left-0 z-10 border-b border-gray-100 bg-white px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                    {t('Period')}
                  </th>
                  {WEEK_DAYS.map((d) => (
                    <th
                      key={d.value}
                      className="border-b border-l border-gray-100 px-3 py-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500"
                    >
                      {t(d.label)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {teachingPeriods.map((p) => (
                  <tr key={p.id} className="border-b border-gray-100 last:border-0">
                    <th className="sticky left-0 z-10 bg-white px-3 py-2 text-left align-top">
                      <span className="block text-sm font-medium text-gray-900">{periodLabel(p)}</span>
                      <span className="block text-xs text-gray-400">
                        {shortTime(p.start_time)}–{shortTime(p.end_time)}
                      </span>
                    </th>
                    {WEEK_DAYS.map((d) => {
                      const row = cells.get(`${d.value}:${p.id}`);
                      return (
                        <td key={d.value} className="border-l border-gray-100 p-0 align-top">
                          <button
                            type="button"
                            onClick={() => openCell(d.value, p)}
                            disabled={!mayEdit}
                            className={`flex min-h-[64px] w-full flex-col justify-center px-3 py-2 text-left ${
                              mayEdit ? 'hover:bg-blue-50' : 'cursor-default'
                            }`}
                          >
                            {cellContent(row)}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={
          draft
            ? `${chosenClass ? classLabel(chosenClass) : ''} · ${t(WEEK_DAYS[draft.day].label)} · ${periodLabel(periods.find((p) => p.id === draft.period))}`
            : ''
        }
        maxWidth="lg"
        footer={
          <div className="flex gap-2">
            {draft?.id !== null && mayDelete && (
              <button
                type="button"
                onClick={() => void clearCell()}
                disabled={saving}
                className="tap rounded-lg border border-red-200 px-4 text-sm font-medium text-red-700 hover:bg-red-50"
              >
                {t('Clear')}
              </button>
            )}
            <button type="button" onClick={() => setDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving || !draft?.subject || !draft?.teacher}
              className={`${btnPrimary} flex-1`}
            >
              {saving ? t('Saving…') : t('Save')}
            </button>
          </div>
        }
      >
        {draft && (
          <div className="space-y-4">
            <FormError message={formError} />

            <Field label={t('Subject')} error={fieldErrors.subject} required>
              <select
                value={draft.subject}
                onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
                className={selectCls}
              >
                <option value="">{t('Choose a subject')}</option>
                {subjects.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name_bn || s.name}
                  </option>
                ))}
              </select>
            </Field>

            <Field label={t('Teacher')} error={fieldErrors.teacher} required>
              <select
                value={draft.teacher}
                onChange={(e) => setDraft({ ...draft, teacher: e.target.value })}
                className={selectCls}
              >
                <option value="">{t('Choose a teacher')}</option>
                {data.teachers.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name_bn || x.name}
                  </option>
                ))}
              </select>
            </Field>

            {/* Shown the moment the teacher is picked, so the clash is a choice
                to reconsider rather than a rejection after Save. */}
            {liveClash && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {`${liveClash.teacher} ${t('already teaches')} ${liveClash.className} ${t('at this time.')}`}
              </p>
            )}

            <Field label={t('Room')} error={fieldErrors.room}>
              <input
                value={draft.room}
                onChange={(e) => setDraft({ ...draft, room: e.target.value })}
                className={inputCls}
              />
            </Field>
          </div>
        )}
      </BaseModal>
    </div>
  );
}
