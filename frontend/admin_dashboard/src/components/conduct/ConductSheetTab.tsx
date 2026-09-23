import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  AcademicClass,
  ConductItem,
  ConductRowInput,
  ConductSaveResult,
  ConductSheet,
  ConductStudent,
  ConductValue,
  ReportTemplate,
  Section,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';
import { todayInDhaka } from '../../lib/timezone';
import Picker from '../common/Picker';
import { preferredClassId, useOwnTeacherId } from '../../lib/defaults';
import {
  cycleYesNo,
  displayValue,
  effectiveAnswer,
  effectiveRemarks,
  itemLabel,
  itemOptions,
  sameValue,
  studentName,
} from './shared';
import type { DraftRow } from './shared';

/**
 * The observation register — `docs/02` §4.10, and the same screen as the
 * attendance month register because it is the same act: a teacher in front of a
 * class, recording one small thing per student.
 *
 * Four things about it are decisions, not decoration:
 *
 * **It asks nothing it already knows** (`CLAUDE.md` §7b). The class defaults to
 * the teacher's own, the date to today, and the template to whatever the server
 * says is most specific for that class — so the screen opens on a filled-in
 * sheet with every picker hidden, and *another class* reveals them.
 *
 * **A yes/no is one tap.** নামাজ is the question this register exists for and a
 * class is forty boys; anything more than a tap per boy is a screen nobody
 * finishes. The cell cycles ✓ → ✗ → blank, and the column header marks the
 * whole class at once, which is how it actually goes: everyone prayed, then
 * correct the three who did not.
 *
 * **Only the dirty rows are sent.** The endpoint writes what it is given and
 * leaves the rest, so an untouched student is not re-stamped with today's
 * filler and a class of sixty is a small request on a phone.
 *
 * **Two layouts, not one that shrinks.** From `md` up it is the grid: students
 * down, questions across, first column frozen. Below `md` it is ONE STUDENT
 * with prev/next arrows (§7a), because a grid is not usable with a thumb; the
 * grid stays behind a toggle for anyone who would rather pinch and scroll.
 */

interface Props {
  classes: AcademicClass[];
  sections: Section[];
  /** The templates, when the reader may list them. A teacher holds `conduct`
   *  and not `settings`, so for most of this screen's users the list is empty
   *  and the server's own choice is the only one — which is the right answer
   *  anyway. */
  templates: ReportTemplate[];
  onSectionsNeeded: (classId: string) => void;
}

type PhoneView = 'student' | 'grid';

/**
 * The same control, without `w-full`.
 *
 * Tailwind emits `w-full` after the fixed widths, so `${inputCls} w-20` renders
 * full width whatever order the attribute lists — the class attribute does not
 * decide which rule wins, the stylesheet does. Dropping it is what lets a grid
 * cell be 5rem wide instead of as wide as its column can stretch.
 */
const gridInputCls = inputCls.replace('w-full ', '');

export default function ConductSheetTab({
  classes,
  sections,
  templates,
  onSectionsNeeded,
}: Props) {
  const { t, lang } = useT();
  const { can } = usePermissions();

  const [classChoice, setClassChoice] = useState('');
  const [sectionId, setSectionId] = useState('');
  const [templateChoice, setTemplateChoice] = useState('');
  const [date, setDate] = useState(() => todayInDhaka());
  /** The pickers start hidden because every one of them already holds the
   *  right answer (§7b rule 4). Covering a colleague is real, but it is the
   *  exception, and it should not cost four decisions every morning. */
  const [showPickers, setShowPickers] = useState(false);

  const [sheet, setSheet] = useState<ConductSheet | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<Map<number, DraftRow>>(new Map());
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [result, setResult] = useState<ConductSaveResult | null>(null);

  const [phoneView, setPhoneView] = useState<PhoneView>('student');
  const [studentIndex, setStudentIndex] = useState(0);

  const mayEdit = can('conduct', 'take') || can('conduct', 'update');

  const ownTeacherId = useOwnTeacherId();
  const classId = classes.some((c) => String(c.id) === classChoice)
    ? classChoice
    : preferredClassId(classes, ownTeacherId);

  const classSections = useMemo(
    () => sections.filter((s) => String(s.academic_class) === classId),
    [sections, classId],
  );

  /** The templates this class could be observed with. A narrowed one belongs to
   *  its own class or বিভাগ and must not be offered anywhere else — the server
   *  applies the same rule when it picks for us. */
  const classTemplates = useMemo(() => {
    const chosen = classes.find((c) => String(c.id) === classId);
    return templates.filter(
      (tpl) => tpl.is_active
        && (tpl.academic_class === null || String(tpl.academic_class) === classId)
        && (tpl.stream === null || (chosen != null && tpl.stream === chosen.stream)),
    );
  }, [templates, classes, classId]);

  const templateId = classTemplates.some((tpl) => String(tpl.id) === templateChoice)
    ? templateChoice
    : '';

  useEffect(() => {
    if (classId) onSectionsNeeded(classId);
  }, [classId, onSectionsNeeded]);

  /* Switching class mid-flight must never write one class's answers onto
   * another's sheet: two requests race and the slower wins by landing last. */
  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    if (!classId) {
      setSheet(null);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const data = await apiClient.getConductSheet({
        academicClass: Number(classId),
        date,
        template: templateId ? Number(templateId) : null,
        section: sectionId ? Number(sectionId) : null,
      });
      if (!req.isCurrent(mine)) return;
      setSheet(data);
      // The draft belongs to the sheet that has just been replaced. The confirm
      // that protects it is on the controls that cause the reload.
      setDraft(new Map());
      setResult(null);
      setStudentIndex(0);
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setSheet(null);
      setLoadError(apiErrorText(err, t, t('Could not load the conduct sheet.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [classId, sectionId, templateId, date, req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  // ── Editing ─────────────────────────────────────────────────────────────

  const setAnswer = useCallback(
    (student: ConductStudent, itemId: number, value: ConductValue) => {
      if (!mayEdit) return;
      setDraft((prev) => {
        const next = new Map(prev);
        const row: DraftRow = next.get(student.enrolment)
          ?? { answers: {}, remarks: student.remarks ?? '' };
        const answers = { ...row.answers };
        const saved = student.answers[String(itemId)] ?? null;
        if (sameValue(saved, value)) delete answers[String(itemId)];
        else answers[String(itemId)] = value;

        const remarksChanged = row.remarks !== (student.remarks ?? '');
        if (Object.keys(answers).length === 0 && !remarksChanged) next.delete(student.enrolment);
        else next.set(student.enrolment, { ...row, answers });
        return next;
      });
    },
    [mayEdit],
  );

  const setRemarks = useCallback(
    (student: ConductStudent, remarks: string) => {
      if (!mayEdit) return;
      setDraft((prev) => {
        const next = new Map(prev);
        const row: DraftRow = next.get(student.enrolment)
          ?? { answers: {}, remarks: student.remarks ?? '' };
        if (remarks === (student.remarks ?? '') && Object.keys(row.answers).length === 0) {
          next.delete(student.enrolment);
        } else {
          next.set(student.enrolment, { ...row, remarks });
        }
        return next;
      });
    },
    [mayEdit],
  );

  /** The column bulk action — everyone prayed, then correct the three who did
   *  not. Only for a yes/no, because it is the only question with an answer
   *  that is true of a whole class often enough to be worth one control. */
  const markWholeColumn = (item: ConductItem, value: boolean) => {
    if (!sheet || !mayEdit) return;
    for (const student of sheet.students) setAnswer(student, item.id, value);
  };

  // ── Saving ──────────────────────────────────────────────────────────────

  const save = async () => {
    if (!sheet || draft.size === 0) return;
    setSaving(true);
    setSaveError(null);
    const rows: ConductRowInput[] = [...draft.entries()].map(([enrolment, row]) => ({
      enrolment,
      answers: row.answers,
      // Always sent, changed or not: the endpoint writes the remark it is
      // given, so leaving it out of a row that only changed an answer would
      // blank a note somebody wrote yesterday.
      remarks: row.remarks,
    }));
    try {
      const saved = await apiClient.saveConductSheet({
        academicClass: sheet.academic_class,
        date,
        template: sheet.template,
        section: sectionId ? Number(sectionId) : null,
        rows,
      });
      // Re-read rather than patching: `filled_by` and `filled_at` changed, and
      // a sheet showing a stale filler answers "who marked my son" wrongly.
      await load();
      setResult(saved);
    } catch (err) {
      setSaveError(apiErrorText(err, t, t('Could not save the conduct sheet.')));
    } finally {
      setSaving(false);
    }
  };

  // ── Cells ───────────────────────────────────────────────────────────────

  const isDirty = (student: ConductStudent, itemId: number) =>
    Object.prototype.hasOwnProperty.call(
      draft.get(student.enrolment)?.answers ?? {},
      String(itemId),
    );

  /**
   * One answer, drawn as its type wants to be answered.
   *
   * `compact` is the grid; the phone view gets the roomier form of the same
   * control — chips instead of a dropdown, a full-width box instead of a
   * 5rem one — because there is width for it and a thumb needs it.
   */
  const cell = (student: ConductStudent, item: ConductItem, compact: boolean) => {
    const value = effectiveAnswer(student, item.id, draft);
    const dirty = isDirty(student, item.id);
    const ring = dirty ? 'ring-2 ring-inset ring-blue-400' : '';
    const options = itemOptions(item, lang);

    if (item.type === 'yes_no') {
      const tone = value === true
        ? 'bg-green-100 text-green-800'
        : value === false
          ? 'bg-red-100 text-red-800'
          : 'bg-white text-gray-300';
      return (
        <button
          type="button"
          disabled={!mayEdit}
          onClick={() => setAnswer(student, item.id, cycleYesNo(value))}
          aria-label={`${studentName(student)} · ${itemLabel(item, lang)} · ${displayValue(item, value, t)}`}
          className={`${compact ? 'h-11 w-14' : 'h-12 w-full'} rounded-md border border-gray-200 text-base font-semibold disabled:cursor-not-allowed ${tone} ${ring}`}
        >
          {value === true ? '✓' : value === false ? '✗' : '–'}
        </button>
      );
    }

    if (item.type === 'single_choice') {
      if (!compact) {
        return (
          <div className="flex flex-wrap gap-1.5">
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                disabled={!mayEdit}
                onClick={() => setAnswer(
                  student,
                  item.id,
                  value === option.value ? null : option.value,
                )}
                aria-pressed={value === option.value}
                className={`tap rounded-md border px-3 text-[13px] font-medium ${
                  value === option.value
                    ? `border-transparent bg-blue-600 text-white ${ring}`
                    : 'border-gray-200 bg-white text-gray-600'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        );
      }
      return (
        <select
          disabled={!mayEdit}
          value={value === null ? '' : String(value)}
          onChange={(e) => setAnswer(student, item.id, e.target.value || null)}
          aria-label={`${studentName(student)} · ${itemLabel(item, lang)}`}
          className={`${gridInputCls} min-w-[7rem] ${ring}`}
        >
          <option value="">—</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    }

    if (item.type === 'multi_choice') {
      const chosen = Array.isArray(value) ? value.map(String) : [];
      return (
        <div className="flex flex-wrap gap-1.5">
          {options.map((option) => {
            const on = chosen.includes(option.value);
            return (
              <button
                key={option.value}
                type="button"
                disabled={!mayEdit}
                onClick={() => setAnswer(
                  student,
                  item.id,
                  on ? chosen.filter((v) => v !== option.value) : [...chosen, option.value],
                )}
                aria-pressed={on}
                className={`tap rounded-md border px-2.5 text-[13px] font-medium ${
                  on
                    ? `border-transparent bg-blue-600 text-white ${ring}`
                    : 'border-gray-200 bg-white text-gray-600'
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      );
    }

    if (item.type === 'number') {
      return (
        <input
          type="number"
          inputMode="numeric"
          disabled={!mayEdit}
          value={value === null ? '' : String(value)}
          onChange={(e) => setAnswer(
            student,
            item.id,
            e.target.value === '' ? null : Number(e.target.value),
          )}
          aria-label={`${studentName(student)} · ${itemLabel(item, lang)}`}
          className={`${compact ? `${gridInputCls} w-20` : inputCls} ${ring}`}
        />
      );
    }

    if (item.type === 'date') {
      return (
        <input
          type="date"
          disabled={!mayEdit}
          value={value === null ? '' : String(value)}
          onChange={(e) => setAnswer(student, item.id, e.target.value || null)}
          aria-label={`${studentName(student)} · ${itemLabel(item, lang)}`}
          className={`${compact ? `${gridInputCls} w-36` : inputCls} ${ring}`}
        />
      );
    }

    // short_text and description. The server bounds it at 200 characters, so
    // the box does too rather than letting a paste be silently cut.
    return (
      <input
        type="text"
        maxLength={200}
        disabled={!mayEdit}
        value={value === null ? '' : String(value)}
        onChange={(e) => setAnswer(student, item.id, e.target.value)}
        aria-label={`${studentName(student)} · ${itemLabel(item, lang)}`}
        className={`${compact ? `${gridInputCls} w-40` : inputCls} ${ring}`}
      />
    );
  };

  // ── Layouts ─────────────────────────────────────────────────────────────

  const items = sheet?.items ?? [];
  const students = sheet?.students ?? [];
  const student = students[Math.min(studentIndex, Math.max(0, students.length - 1))];

  const grid = sheet && (
    // The one container allowed to scroll sideways — the body never does
    // (`CLAUDE.md` §7a rule 1).
    <div className="scroll-x rounded-xl border border-gray-100 bg-white shadow-sm">
      <table className="border-collapse">
        <thead>
          <tr>
            <th className="sticky left-0 z-20 min-w-[10rem] border-b border-r border-gray-200 bg-white px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              {t('Student')}
            </th>
            {items.map((item) => (
              <th
                key={item.id}
                className="border-b border-gray-100 px-2 py-2 text-center text-xs font-medium text-gray-600"
              >
                <span className="block max-w-[10rem] whitespace-normal">
                  {itemLabel(item, lang)}
                </span>
                {item.type === 'yes_no' && (
                  <span className="mt-1 flex justify-center gap-1">
                    <button
                      type="button"
                      disabled={!mayEdit}
                      onClick={() => markWholeColumn(item, true)}
                      title={t('Mark all yes')}
                      aria-label={`${t('Mark all yes')} — ${itemLabel(item, lang)}`}
                      className="min-h-[28px] rounded px-2 text-[11px] leading-none text-green-700 hover:bg-green-50 disabled:invisible"
                    >
                      ✓
                    </button>
                    <button
                      type="button"
                      disabled={!mayEdit}
                      onClick={() => markWholeColumn(item, false)}
                      title={t('Mark all no')}
                      aria-label={`${t('Mark all no')} — ${itemLabel(item, lang)}`}
                      className="min-h-[28px] rounded px-2 text-[11px] leading-none text-red-700 hover:bg-red-50 disabled:invisible"
                    >
                      ✗
                    </button>
                  </span>
                )}
              </th>
            ))}
            <th className="border-b border-l border-gray-200 px-2 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
              {t('Remarks')}
            </th>
          </tr>
        </thead>
        <tbody>
          {students.map((row) => (
            <tr key={row.enrolment} className="border-b border-gray-100 last:border-0">
              {/* Frozen first column: the name stays readable while the
                  questions scroll under the thumb (§7a). */}
              <th className="sticky left-0 z-10 min-w-[10rem] border-r border-gray-200 bg-white px-3 py-1.5 text-left">
                <span className="block truncate text-sm font-medium text-gray-900">
                  {studentName(row)}
                </span>
                <span className="block text-[11px] text-gray-400">
                  {row.roll ?? '—'}
                  {row.filled && ` · ${t('Filled')}`}
                </span>
              </th>
              {items.map((item) => (
                <td key={item.id} className="px-2 py-1 text-center">
                  {cell(row, item, true)}
                </td>
              ))}
              <td className="border-l border-gray-200 px-2 py-1">
                <input
                  type="text"
                  maxLength={200}
                  disabled={!mayEdit}
                  value={effectiveRemarks(row, draft)}
                  onChange={(e) => setRemarks(row, e.target.value)}
                  aria-label={`${t('Remarks')} — ${studentName(row)}`}
                  className={`${gridInputCls} w-44`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const oneStudent = sheet && student && (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 rounded-xl border border-gray-100 bg-white p-2 shadow-sm">
        <button
          type="button"
          onClick={() => setStudentIndex(Math.max(0, studentIndex - 1))}
          disabled={studentIndex === 0}
          className={btnSecondary}
          aria-label={t('Previous student')}
        >
          ‹
        </button>
        <div className="min-w-0 text-center">
          <span className="block truncate text-sm font-semibold text-gray-900">
            {studentName(student)}
          </span>
          <span className="block text-xs text-gray-500">
            {`${t('Roll')} ${student.roll ?? '—'} · ${studentIndex + 1}/${students.length}`}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setStudentIndex(Math.min(students.length - 1, studentIndex + 1))}
          disabled={studentIndex >= students.length - 1}
          className={btnSecondary}
          aria-label={t('Next student')}
        >
          ›
        </button>
      </div>

      <div className="space-y-3 rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
        {items.map((item) => (
          <div key={item.id}>
            <span className="mb-1 block text-sm font-medium text-gray-700">
              {itemLabel(item, lang)}
            </span>
            {cell(student, item, false)}
          </div>
        ))}
        <div>
          <span className="mb-1 block text-sm font-medium text-gray-700">{t('Remarks')}</span>
          <input
            type="text"
            maxLength={200}
            disabled={!mayEdit}
            value={effectiveRemarks(student, draft)}
            onChange={(e) => setRemarks(student, e.target.value)}
            aria-label={`${t('Remarks')} — ${studentName(student)}`}
            className={inputCls}
          />
        </div>
      </div>
    </div>
  );

  /** Anything that reloads the sheet throws the unsaved answers away, so it
   *  asks first — and only when there is something to lose. */
  const leavingDraft = (go: () => void) => {
    if (draft.size > 0
        && !window.confirm(t('You have unsaved answers on this sheet. Leave them?'))) {
      return;
    }
    go();
  };

  const chosenClass = classes.find((c) => String(c.id) === classId);

  return (
    <div className="space-y-4">
      {/* ── What this sheet is, and how to change it ───────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-100 bg-white px-3 py-2 shadow-sm">
        <div className="min-w-0">
          <span className="block truncate text-sm font-semibold text-gray-900">
            {chosenClass ? chosenClass.name_bn || chosenClass.name : t('No class')}
            {sheet && ` · ${sheet.template_name}`}
          </span>
          <span className="block text-xs text-gray-500">
            {sheet ? `${t('Period')}: ${sheet.period}` : date}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setShowPickers(!showPickers)}
          className={btnSecondary}
        >
          {showPickers ? t('Done') : t('Another class')}
        </button>
      </div>

      {showPickers && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-gray-700">{t('Class')}</span>
            <Picker
              value={classId}
              onChange={(v) => leavingDraft(() => {
                setClassChoice(v);
                setSectionId('');
                setTemplateChoice('');
              })}
              options={classes.map((c) => ({ value: String(c.id), label: c.name_bn || c.name }))}
              emptyLabel={t('No classes are assigned to you.')}
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-gray-700">{t('Section')}</span>
            <Picker
              value={sectionId}
              onChange={(v) => leavingDraft(() => setSectionId(v))}
              options={classSections.map((s) => ({ value: String(s.id), label: s.name_bn || s.name }))}
              anyLabel={t('Whole class')}
            />
          </label>

          {/* Only for somebody who may list templates at all, and only when
              there is more than one — a dropdown with one entry is a control
              that cannot do anything (§7b rule 3). */}
          {classTemplates.length > 1 && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-700">{t('Report')}</span>
              <Picker
                value={templateId}
                onChange={(v) => leavingDraft(() => setTemplateChoice(v))}
                options={classTemplates.map((tpl) => ({
                  value: String(tpl.id),
                  label: tpl.name_bn || tpl.name,
                }))}
                anyLabel={t('Automatic')}
              />
            </label>
          )}

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-gray-700">{t('Date')}</span>
            <input
              type="date"
              value={date}
              onChange={(e) => e.target.value && leavingDraft(() => setDate(e.target.value))}
              className={inputCls}
            />
          </label>
        </div>
      )}

      {loadError && <FormError message={loadError} />}
      {saveError && <FormError message={saveError} />}

      {result && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {`${t('Saved')}: ${result.saved} · ${t('Period')}: ${result.period}`}
        </div>
      )}

      {/* The server refused these and says why per row. Shown in full rather
          than counted — a teacher can only act on a named student. */}
      {result && result.skipped.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p className="font-medium">{`${t('Not saved')}: ${result.skipped.length}`}</p>
          <ul className="mt-1 space-y-0.5">
            {result.skipped.map((row, index) => {
              const who = students.find((s) => s.enrolment === row.enrolment);
              return (
                <li key={`${row.enrolment}-${row.item ?? index}`}>
                  {`${who ? studentName(who) : row.enrolment} — ${
                    row.reason === 'not_enrolled'
                      ? t('Not enrolled in this class.')
                      : t('That question is not on this sheet.')
                  }`}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {!mayEdit && (
        <p className="text-sm text-gray-500">
          {t('You can read this sheet but not fill it.')}
        </p>
      )}

      {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {!loading && sheet && items.length === 0 && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('This report has no questions yet. Add them on Settings → Questions.')}
        </div>
      )}

      {!loading && sheet && students.length === 0 && (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('No students are enrolled in this class.')}
        </div>
      )}

      {sheet && items.length > 0 && students.length > 0 && (
        <>
          {/* ── Phone: one student at a time, the grid behind a toggle ───── */}
          <div className="md:hidden">
            <div className="mb-3 flex items-center justify-end">
              <button
                type="button"
                onClick={() => setPhoneView(phoneView === 'student' ? 'grid' : 'student')}
                className={btnSecondary}
              >
                {phoneView === 'student' ? t('Grid view') : t('One student')}
              </button>
            </div>
            {phoneView === 'student' ? oneStudent : grid}
          </div>

          {/* ── md and up: the register itself ──────────────────────────── */}
          <div className="hidden md:block">{grid}</div>
        </>
      )}

      {/* Sticks to the bottom so Save is reachable with a thumb after forty
          rows of scrolling, and clears the home indicator (§7a rule 9). */}
      {sheet && draft.size > 0 && (
        <div className="sticky bottom-0 z-30 -mx-4 border-t border-gray-200 bg-white/95 px-4 pb-[env(safe-area-inset-bottom)] pt-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
          <div className="flex items-center justify-between gap-3 pb-3">
            <span className="text-sm text-gray-600">
              {`${draft.size} ${t('students changed')}`}
            </span>
            <span className="flex gap-2">
              <button type="button" onClick={() => setDraft(new Map())} className={btnSecondary}>
                {t('Discard')}
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving}
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
