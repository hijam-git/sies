import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Subject } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import Picker from '../common/Picker';
import { preferredClassId, useOwnTeacherId } from '../../lib/defaults';
import { classLabel } from './shared';
import type { AcademicsData } from './shared';

/**
 * Subjects, under one chosen class.
 *
 * A subject belongs to a class rather than floating free, which is what makes
 * the routine and the marks entry able to offer a short, correct list instead
 * of every subject the institution teaches.
 */

interface SubjectDraft {
  stream: string;
  name: string;
  name_bn: string;
  code: string;
  full_marks: string;
  pass_marks: string;
  is_optional: boolean;
  has_practical: boolean;
  practical_marks: string;
  is_active: boolean;
}

function emptyDraft(stream: string): SubjectDraft {
  return {
    stream,
    name: '',
    name_bn: '',
    code: '',
    full_marks: '100',
    pass_marks: '33',
    is_optional: false,
    has_practical: false,
    practical_marks: '0',
    is_active: true,
  };
}

export default function SubjectsTab({ data }: { data: AcademicsData }) {
  const { t } = useT();
  const { can } = usePermissions();

  // The CHOICE, with the first class as the fallback. Derived rather than
  // seeded from an effect, which would render once with nothing chosen and
  // again with the default.
  const [classChoice, setClassChoice] = useState<string>('');
  const [rows, setRows] = useState<Subject[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<SubjectDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('academics', 'create');
  const mayUpdate = can('academics', 'update');
  const mayDelete = can('academics', 'delete');

  // Same preference as Sections: their own class first, then the list's order.
  const ownTeacherId = useOwnTeacherId(data.teachers);
  const classId = data.classes.some((c) => String(c.id) === classChoice)
    ? classChoice
    : preferredClassId(data.classes, ownTeacherId);

  const load = useCallback(async () => {
    if (!classId) {
      setRows([]);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      setRows(await apiClient.listAll<Subject>('/subjects/', `?academic_class=${classId}`));
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the subjects.')));
    } finally {
      setLoading(false);
    }
  }, [classId, t]);

  // Deferred by a tick rather than called from the effect body: `load` sets
  // state synchronously, which during an effect cascades a render before the
  // first paint. The same shape the other list screens use.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const chosenClass = data.classes.find((c) => String(c.id) === classId);

  const openCreate = () => {
    setEditingId(null);
    // Seeded from the class's own stream: a subject in a Hifz class is a Hifz
    // subject nearly every time, and re-picking it per subject is typing.
    setDraft(emptyDraft(chosenClass?.stream === null || chosenClass === undefined ? '' : String(chosenClass.stream)));
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (row: Subject) => {
    setEditingId(row.id);
    setDraft({
      stream: row.stream === null ? '' : String(row.stream),
      name: row.name,
      name_bn: row.name_bn,
      code: row.code,
      full_marks: String(row.full_marks),
      pass_marks: String(row.pass_marks),
      is_optional: row.is_optional,
      has_practical: row.has_practical,
      practical_marks: String(row.practical_marks),
      is_active: row.is_active,
    });
    setFormError(null);
    setFieldErrors({});
  };

  const save = async () => {
    if (!draft || !classId) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      academic_class: Number(classId),
      stream: draft.stream ? Number(draft.stream) : null,
      name: draft.name.trim(),
      name_bn: draft.name_bn.trim(),
      code: draft.code.trim(),
      full_marks: Number(draft.full_marks || 0),
      pass_marks: Number(draft.pass_marks || 0),
      is_optional: draft.is_optional,
      has_practical: draft.has_practical,
      practical_marks: draft.has_practical ? Number(draft.practical_marks || 0) : 0,
      is_active: draft.is_active,
    };
    try {
      if (editingId !== null) await apiClient.patch<Subject>('/subjects/', editingId, body);
      else await apiClient.create<Subject>('/subjects/', body);
      setDraft(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this subject.')));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row: Subject) => {
    if (!window.confirm(t('Delete this subject?'))) return;
    try {
      await apiClient.destroy('/subjects/', row.id);
      await load();
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not delete this subject.')));
    }
  };

  const columns: Column<Subject>[] = [
    {
      key: 'name',
      label: t('Subject'),
      primary: true,
      render: (s) => (
        <span className="block">
          <span className="block">{s.name_bn || s.name}</span>
          {s.code && <span className="block font-mono text-xs text-gray-500">{s.code}</span>}
        </span>
      ),
    },
    { key: 'full', label: t('Full marks'), render: (s) => s.full_marks },
    { key: 'pass', label: t('Pass marks'), render: (s) => s.pass_marks },
    {
      key: 'practical',
      label: t('Practical'),
      hideOnNarrow: true,
      render: (s) => (s.has_practical ? s.practical_marks : '—'),
    },
    {
      key: 'optional',
      label: t('Optional'),
      render: (s) => (s.is_optional ? t('Yes') : t('No')),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      headClass: 'px-4 py-3 text-right',
      render: (s) => (
        <span className="inline-flex gap-2">
          {mayUpdate && (
            <button type="button" onClick={() => openEdit(s)} className={btnSecondary}>
              {t('Edit')}
            </button>
          )}
          {mayDelete && (
            <button
              type="button"
              onClick={() => void remove(s)}
              className="tap rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50"
            >
              {t('Delete')}
            </button>
          )}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-full sm:w-64">
          <Field label={t('Class')}>
            <Picker
              value={classId}
              onChange={setClassChoice}
              options={data.classes.map((c) => ({
                value: String(c.id),
                label: `${classLabel(c)} · ${c.year}`,
              }))}
              emptyLabel={t('Choose a class')}
            />
          </Field>
        </div>
        {mayCreate && classId && (
          <button type="button" onClick={openCreate} className={btnPrimary}>
            {t('Add subject')}
          </button>
        )}
      </div>

      {loadError && <FormError message={loadError} />}

      <ResponsiveTable
        columns={columns}
        rows={rows}
        rowKey={(s) => s.id}
        empty={
          loading
            ? t('Loading…')
            : classId
              ? t('This class has no subjects yet.')
              : t('Choose a class to see its subjects.')
        }
      />

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId === null ? t('Add subject') : t('Edit subject')}
        maxWidth="2xl"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button type="button" onClick={() => void save()} disabled={saving} className={`${btnPrimary} flex-1`}>
              {saving ? t('Saving…') : t('Save')}
            </button>
          </div>
        }
      >
        {draft && (
          <div className="space-y-4">
            <FormError message={formError} />
            <FieldGrid>
              <Field label={t('Name (English)')} error={fieldErrors.name} required>
                <input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Name (Bangla)')} error={fieldErrors.name_bn} required>
                <input
                  value={draft.name_bn}
                  onChange={(e) => setDraft({ ...draft, name_bn: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Code')} error={fieldErrors.code}>
                <input
                  value={draft.code}
                  onChange={(e) => setDraft({ ...draft, code: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Stream')} error={fieldErrors.stream}>
                <select
                  value={draft.stream}
                  onChange={(e) => setDraft({ ...draft, stream: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Every stream')}</option>
                  {data.streams.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name_bn || s.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Full marks')} error={fieldErrors.full_marks} required>
                <input
                  type="number"
                  inputMode="numeric"
                  value={draft.full_marks}
                  onChange={(e) => setDraft({ ...draft, full_marks: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Pass marks')} error={fieldErrors.pass_marks} required>
                <input
                  type="number"
                  inputMode="numeric"
                  value={draft.pass_marks}
                  onChange={(e) => setDraft({ ...draft, pass_marks: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Optional subject')}>
                <label className="flex min-h-[44px] items-center gap-3">
                  <input
                    type="checkbox"
                    checked={draft.is_optional}
                    onChange={(e) => setDraft({ ...draft, is_optional: e.target.checked })}
                    className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">{t('Not every student takes it')}</span>
                </label>
              </Field>
              <Field label={t('Has practical')}>
                <label className="flex min-h-[44px] items-center gap-3">
                  <input
                    type="checkbox"
                    checked={draft.has_practical}
                    onChange={(e) => setDraft({ ...draft, has_practical: e.target.checked })}
                    className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">{t('Yes')}</span>
                </label>
              </Field>
              {draft.has_practical && (
                <Field label={t('Practical marks')} error={fieldErrors.practical_marks}>
                  <input
                    type="number"
                    inputMode="numeric"
                    value={draft.practical_marks}
                    onChange={(e) => setDraft({ ...draft, practical_marks: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              )}
              <Field label={t('Status')}>
                <label className="flex min-h-[44px] items-center gap-3">
                  <input
                    type="checkbox"
                    checked={draft.is_active}
                    onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                    className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">{t('Active')}</span>
                </label>
              </Field>
            </FieldGrid>
          </div>
        )}
      </BaseModal>
    </div>
  );
}
