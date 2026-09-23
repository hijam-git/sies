import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  AcademicClass,
  ReportAssignment,
  ReportTemplate,
  Section,
  Teacher,
} from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import useRequestId from '../../lib/useRequestId';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FormError } from '../common/Field';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { btnPrimary, btnRowAction, btnSecondary, selectCls } from '../common/styles';

/**
 * Who is meant to fill each report — `docs/03` §9b's `ReportAssignment`.
 *
 * **Responsibility, not exclusivity.** It decides whose screen opens on which
 * sheet and who has their name against one nobody filled; it does not stop a
 * colleague covering for them, and the wording here must never suggest it
 * does. Locking a sheet to one person means it simply goes unfilled on the day
 * they are ill, which is the opposite of what an institution wants from it.
 *
 * শাখা is optional and empty means the whole class — so a class may have both
 * its own teacher per শাখা and one covering all of them, and both names show
 * on the sheet.
 */

interface Draft {
  template: string;
  academic_class: string;
  section: string;
  teacher: string;
}

export default function ReportAssignmentsSection({
  templates,
  classes,
  mayEdit,
}: {
  templates: ReportTemplate[];
  classes: AcademicClass[];
  mayEdit: boolean;
}) {
  const { t } = useT();
  const req = useRequestId();

  const [rows, setRows] = useState<ReportAssignment[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  // Keyed by class rather than one list swapped out: the effect below would
  // otherwise have to blank it synchronously for "no class chosen", which is a
  // setState in an effect body and a cascading render. Deriving it on the
  // render path is the same rule every default here follows (§7b).
  const [sectionsByClass, setSectionsByClass] = useState<Record<string, Section[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [draft, setDraft] = useState<Draft | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const mine = req.begin();
    setLoading(true);
    try {
      const [assignments, staff] = await Promise.all([
        apiClient.listAll<ReportAssignment>('/report-assignments/', '?ordering=template'),
        apiClient.listAll<Teacher>('/teachers/', '?is_active=true&ordering=name'),
      ]);
      if (!req.isCurrent(mine)) return;
      setRows(assignments);
      setTeachers(staff);
      setError(null);
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setError(apiErrorText(err, t, t('Could not load who is responsible.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  // The শাখা list follows the class in the form — a class with none simply
  // never offers the picker (§7b rule 3).
  const classId = draft?.academic_class ?? '';
  const sections = sectionsByClass[classId] ?? [];
  useEffect(() => {
    if (!classId) return;
    let live = true;
    void apiClient
      .listAll<Section>('/sections/', `?academic_class=${classId}&is_active=true`)
      .then((found) => { if (live) setSectionsByClass((prev) => ({ ...prev, [classId]: found })); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [classId]);

  const openNew = () => {
    setDraft({
      // One template is not a decision, so it is already made.
      template: templates.length ? String(templates[0].id) : '',
      academic_class: classes.length === 1 ? String(classes[0].id) : '',
      section: '',
      teacher: '',
    });
    setFieldErrors({});
    setFormError(null);
  };

  const save = async () => {
    if (!draft || !draft.template || !draft.academic_class || !draft.teacher) return;
    setBusy(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await apiClient.create<ReportAssignment>('/report-assignments/', {
        template: Number(draft.template),
        academic_class: Number(draft.academic_class),
        // Empty means the whole class, which is NULL to the API — an empty
        // string would be a bad id.
        section: draft.section ? Number(draft.section) : null,
        teacher: Number(draft.teacher),
      });
      setDraft(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save who is responsible.')));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (row: ReportAssignment) => {
    if (!window.confirm(t('Take this teacher off the report?'))) return;
    try {
      await apiClient.destroy('/report-assignments/', row.id);
      await load();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not save who is responsible.')));
    }
  };

  // The API's `*_name` fields are the English `name` column, and this panel
  // sits in a Bangla screen — so the loaded rows supply `name_bn` where they
  // have it and the server's name is the fallback, never the other way round.
  const bengali = <T extends { id: number; name: string; name_bn: string }>(
    rows_: T[], id: number, fallback: string,
  ) => {
    const found = rows_.find((row) => row.id === id);
    return (found && (found.name_bn || found.name)) || fallback;
  };

  const columns: Column<ReportAssignment>[] = [
    {
      key: 'teacher',
      label: t('Teacher'),
      primary: true,
      render: (row) => (
        <span className="font-medium text-gray-900">
          {bengali(teachers, row.teacher, row.teacher_name)}
        </span>
      ),
    },
    {
      key: 'template',
      label: t('Report'),
      render: (row) => bengali(templates, row.template, row.template_name),
    },
    {
      key: 'class',
      label: t('Class'),
      render: (row) => `${bengali(classes, row.academic_class, row.class_name)} · ${
        row.section_name || t('Whole class')}`,
    },
    {
      key: 'actions',
      label: '',
      action: true,
      render: (row) => (mayEdit ? (
        <button type="button" onClick={() => void remove(row)} className={btnRowAction}>
          {t('Remove')}
        </button>
      ) : null),
    },
  ];

  return (
    <section className="space-y-2 rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-gray-900">{t('Responsible teachers')}</h2>
          <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-gray-500">
            {t('Who is meant to fill each report. It does not stop another teacher of that class filling it.')}
          </p>
        </div>
        {mayEdit && templates.length > 0 && (
          <button type="button" onClick={openNew} className={btnSecondary}>
            {t('Give the responsibility')}
          </button>
        )}
      </div>

      <FormError message={error} />

      {loading ? (
        <p className="text-sm text-gray-400">{t('Loading…')}</p>
      ) : (
        <ResponsiveTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          empty={t('Nobody has been given a report yet.')}
        />
      )}

      {draft && (
        <BaseModal
          isOpen
          onClose={() => setDraft(null)}
          title={t('Responsible teachers')}
          maxWidth="lg"
          footer={
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setDraft(null)}
                className={`${btnSecondary} flex-1`}
              >
                {t('Cancel')}
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={busy || !draft.template || !draft.academic_class || !draft.teacher}
                className={`${btnPrimary} flex-1`}
              >
                {t('Save')}
              </button>
            </div>
          }
        >
          <div className="space-y-3">
            <FormError message={formError} />

            <FieldGrid>
              <Field label={t('Report')} error={fieldErrors.template} required>
                {templates.length === 1 ? (
                  // A dropdown with one entry is a control that cannot do
                  // anything (§7b rule 3).
                  <p className="py-2 text-sm text-gray-900">
                    {templates[0].name_bn || templates[0].name}
                  </p>
                ) : (
                  <select
                    value={draft.template}
                    onChange={(e) => setDraft({ ...draft, template: e.target.value })}
                    className={selectCls}
                  >
                    {templates.map((template) => (
                      <option key={template.id} value={template.id}>
                        {template.name_bn || template.name}
                      </option>
                    ))}
                  </select>
                )}
              </Field>

              <Field label={t('Class')} error={fieldErrors.academic_class} required>
                <select
                  value={draft.academic_class}
                  onChange={(e) => setDraft({ ...draft, academic_class: e.target.value, section: '' })}
                  className={selectCls}
                >
                  <option value="">{t('Choose a class')}</option>
                  {classes.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name_bn || row.name}
                    </option>
                  ))}
                </select>
              </Field>

              {sections.length > 0 && (
                <Field
                  label={t('Section')}
                  hint={t('Leave it on the whole class unless one শাখা has its own teacher.')}
                  error={fieldErrors.section}
                >
                  <select
                    value={draft.section}
                    onChange={(e) => setDraft({ ...draft, section: e.target.value })}
                    className={selectCls}
                  >
                    <option value="">{t('Whole class')}</option>
                    {sections.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.name_bn || row.name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}

              <Field label={t('Teacher')} error={fieldErrors.teacher} required>
                <select
                  value={draft.teacher}
                  onChange={(e) => setDraft({ ...draft, teacher: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Choose a teacher')}</option>
                  {teachers.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name_bn || row.name}
                    </option>
                  ))}
                </select>
              </Field>
            </FieldGrid>
          </div>
        </BaseModal>
      )}
    </section>
  );
}
