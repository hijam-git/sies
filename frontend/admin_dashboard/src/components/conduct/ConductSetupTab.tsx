import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  AcademicClass,
  FormQuestion,
  ReportFrequency,
  ReportTemplate,
  Stream,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import useRequestId from '../../lib/useRequestId';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FormError } from '../common/Field';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { btnPrimary, btnRowAction, btnSecondary, inputCls, selectCls } from '../common/styles';
import ReportAssignmentsSection from './ReportAssignmentsSection';
import { asksWholeSection } from './shared';
import TemplateQuestionsEditor from './TemplateQuestionsEditor';

/**
 * What the institution observes — `docs/02` §4.10's template.
 *
 * **There is still no question editor here.** The questions are
 * `forms.Question`, the same bank the admission form draws on, and Settings →
 * Questions is their only editor. What this screen decides is which of them
 * one report asks: the whole of a `section`, or a list chosen for this report
 * alone — because two templates drawing on `conduct` otherwise ask an
 * identical list, which is not what a daily নামাজ sheet and a monthly review
 * want. `TemplateQuestionsEditor` holds that.
 *
 * Below the templates, who is *responsible* for filling each one. That is
 * direction, not a lock — see `ReportAssignmentsSection`.
 *
 * The gate is `settings.update`, not `conduct`: a teacher fills the sheet, and
 * deciding what is on it is the office's act.
 */

const FREQUENCIES: Array<{ value: ReportFrequency; label: string }> = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'term', label: 'Per term' },
];

interface Draft {
  name: string;
  name_bn: string;
  frequency: ReportFrequency;
  section: string;
  stream: string;
  academic_class: string;
  is_active: boolean;
}

function emptyDraft(): Draft {
  return {
    name: '',
    name_bn: '',
    frequency: 'daily',
    // The backend's own default, and the section a fresh institution's আমল
    // questions are written into.
    section: 'conduct',
    stream: '',
    academic_class: '',
    is_active: true,
  };
}

export default function ConductSetupTab({
  classes,
  streams,
}: {
  classes: AcademicClass[];
  streams: Stream[];
}) {
  const { t } = useT();
  const { can } = usePermissions();
  const mayEdit = can('settings', 'update');
  const req = useRequestId();

  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  // The whole bank, not one section: a chosen question may come from any of
  // them, and the editor also needs the section's own list to tell a default
  // apart from a list somebody picked.
  const [bank, setBank] = useState<FormQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState<ReportTemplate | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const mine = req.begin();
    setLoading(true);
    try {
      const [rows, questions] = await Promise.all([
        apiClient.listAll<ReportTemplate>('/report-templates/', '?ordering=name'),
        apiClient.listAll<FormQuestion>('/questions/', '?ordering=order'),
      ]);
      if (!req.isCurrent(mine)) return;
      setTemplates(rows);
      setBank(questions);
      setError(null);
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setError(apiErrorText(err, t, t('Could not load the reports.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const openNew = () => {
    setEditing(null);
    setDraft(emptyDraft());
    setFieldErrors({});
    setFormError(null);
  };

  const openEdit = (template: ReportTemplate) => {
    setEditing(template);
    setDraft({
      name: template.name,
      name_bn: template.name_bn,
      frequency: template.frequency,
      section: template.section,
      stream: template.stream === null ? '' : String(template.stream),
      academic_class: template.academic_class === null ? '' : String(template.academic_class),
      is_active: template.is_active,
    });
    setFieldErrors({});
    setFormError(null);
  };

  const save = async () => {
    if (!draft || !draft.name.trim()) return;
    setBusy(true);
    setFormError(null);
    setFieldErrors({});
    const body = {
      name: draft.name.trim(),
      name_bn: draft.name_bn.trim(),
      frequency: draft.frequency,
      section: draft.section.trim() || 'conduct',
      // Empty means EVERY বিভাগ / every class, which is what null says to the
      // API — an empty string would be a bad id.
      stream: draft.stream ? Number(draft.stream) : null,
      academic_class: draft.academic_class ? Number(draft.academic_class) : null,
      is_active: draft.is_active,
    };
    try {
      if (editing) await apiClient.patch<ReportTemplate>('/report-templates/', editing.id, body);
      else await apiClient.create<ReportTemplate>('/report-templates/', body);
      setDraft(null);
      setEditing(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this report.')));
    } finally {
      setBusy(false);
    }
  };

  const streamName = (id: number | null) => {
    if (id === null) return t('Every বিভাগ');
    const stream = streams.find((s) => s.id === id);
    return stream ? stream.name_bn || stream.name : String(id);
  };

  const className = (id: number | null) => {
    if (id === null) return t('Every class');
    const row = classes.find((c) => c.id === id);
    return row ? row.name_bn || row.name : String(id);
  };

  const onItsSection = (row: ReportTemplate) => asksWholeSection(row, bank);

  const columns: Column<ReportTemplate>[] = [
    {
      key: 'name',
      label: t('Report'),
      primary: true,
      render: (row) => (
        <span className="font-medium text-gray-900">{row.name_bn || row.name}</span>
      ),
    },
    {
      key: 'frequency',
      label: t('How often'),
      render: (row) => t(FREQUENCIES.find((f) => f.value === row.frequency)?.label ?? row.frequency),
    },
    {
      key: 'scope',
      label: t('Applies to'),
      render: (row) => `${streamName(row.stream)} · ${className(row.academic_class)}`,
    },
    {
      key: 'section',
      label: t('Questions'),
      // "asks all 4 of section conduct" and "asks 2 chosen questions" are two
      // different things to whoever edits this next, so the list says which.
      render: (row) => (onItsSection(row)
        ? `${t('Asks every question in section')} “${row.section}” · ${row.item_count}`
        : `${t('Asks its own chosen questions')} · ${row.item_count}`),
    },
    {
      key: 'active',
      label: t('Status'),
      hideOnNarrow: true,
      render: (row) => (row.is_active ? t('Active') : t('Inactive')),
    },
    {
      key: 'actions',
      label: '',
      action: true,
      render: (row) => (
        <button type="button" onClick={() => openEdit(row)} className={btnRowAction}>
          {mayEdit ? t('Edit') : t('Open')}
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-sm text-gray-600">
          {t('A report names a section of the question bank, how often it is filled, and which classes it is for.')}
        </p>
        {mayEdit && (
          <button type="button" onClick={openNew} className={btnPrimary}>
            {t('New report')}
          </button>
        )}
      </div>

      <FormError message={error} />

      {loading ? (
        <p className="text-sm text-gray-400">{t('Loading…')}</p>
      ) : (
        <ResponsiveTable
          columns={columns}
          rows={templates}
          rowKey={(row) => row.id}
          onRowClick={openEdit}
          empty={t('No reports yet. A new one takes a name and a question section.')}
        />
      )}

      {draft && (
        <BaseModal
          isOpen
          onClose={() => setDraft(null)}
          title={editing ? editing.name_bn || editing.name : t('New report')}
          maxWidth="2xl"
          footer={
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setDraft(null)}
                className={`${btnSecondary} flex-1`}
              >
                {t('Close')}
              </button>
              {mayEdit && (
                <button
                  type="button"
                  onClick={() => void save()}
                  disabled={busy || !draft.name.trim()}
                  className={`${btnPrimary} flex-1`}
                >
                  {t('Save')}
                </button>
              )}
            </div>
          }
        >
          <div className="space-y-3">
            <FormError message={formError} />

            <FieldGrid>
              <Field label={t('Name')} error={fieldErrors.name} required>
                <input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  disabled={!mayEdit}
                  className={inputCls}
                />
              </Field>
              <Field label={t('নাম')} error={fieldErrors.name_bn}>
                <input
                  value={draft.name_bn}
                  onChange={(e) => setDraft({ ...draft, name_bn: e.target.value })}
                  disabled={!mayEdit}
                  className={inputCls}
                />
              </Field>
              <Field label={t('How often')} error={fieldErrors.frequency}>
                <select
                  value={draft.frequency}
                  onChange={(e) => setDraft({ ...draft, frequency: e.target.value as ReportFrequency })}
                  disabled={!mayEdit}
                  className={selectCls}
                >
                  {FREQUENCIES.map((f) => (
                    <option key={f.value} value={f.value}>
                      {t(f.label)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label={t('Question section')}
                hint={t('The slice of the question bank this sheet asks.')}
                error={fieldErrors.section}
              >
                <input
                  value={draft.section}
                  onChange={(e) => setDraft({ ...draft, section: e.target.value })}
                  disabled={!mayEdit}
                  className={inputCls}
                />
              </Field>
              <Field
                label={t('বিভাগ')}
                hint={t('Leave empty for every one of them.')}
                error={fieldErrors.stream}
              >
                <select
                  value={draft.stream}
                  onChange={(e) => setDraft({ ...draft, stream: e.target.value, academic_class: '' })}
                  disabled={!mayEdit}
                  className={selectCls}
                >
                  <option value="">{t('Every বিভাগ')}</option>
                  {streams.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name_bn || s.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field
                label={t('Class')}
                hint={t('Leave empty for every one of them.')}
                error={fieldErrors.academic_class}
              >
                <select
                  value={draft.academic_class}
                  onChange={(e) => setDraft({ ...draft, academic_class: e.target.value })}
                  disabled={!mayEdit}
                  className={selectCls}
                >
                  <option value="">{t('Every class')}</option>
                  {classes
                    .filter((c) => !draft.stream || String(c.stream) === draft.stream)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name_bn || c.name}
                      </option>
                    ))}
                </select>
              </Field>
            </FieldGrid>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                disabled={!mayEdit}
                className="h-4 w-4"
              />
              <span className="text-sm text-gray-700">{t('Active')}</span>
            </label>

            {/* ── What is on the sheet, and where it is written ─────────── */}
            {editing ? (
              <TemplateQuestionsEditor
                template={editing}
                bank={bank}
                mayEdit={mayEdit}
                onSaved={(saved) => {
                  setEditing(saved);
                  setTemplates((prev) => prev.map((row) => (row.id === saved.id ? saved : row)));
                }}
              />
            ) : (
              <p className="rounded-lg border border-gray-100 bg-gray-50 p-3 text-sm text-gray-500">
                {t('Save the report to choose which questions it asks.')}
              </p>
            )}
          </div>
        </BaseModal>
      )}

      {/* Who is meant to fill these — direction, never a lock. */}
      <ReportAssignmentsSection templates={templates} classes={classes} mayEdit={mayEdit} />
    </div>
  );
}
