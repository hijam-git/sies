import { useState } from 'react';
import { apiClient } from '../../lib/api';
import type { LedgerCategory } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';

/**
 * The heads an income or expense entry is filed under.
 *
 * One component for both, because the two tables are the same shape — the
 * difference is which endpoint it is pointed at.
 *
 * A **seeded** head is switched off, never deleted: the API refuses to destroy
 * one, and an entry from last year points at it anyway. So there is no delete
 * control on a system row at all; the Active checkbox is the whole of what
 * "remove this from the list" means here, and the note in the sheet says so.
 */
export default function CategoryManager({
  path,
  title,
  rows,
  onClose,
  onChanged,
}: {
  path: string;
  title: string;
  rows: LedgerCategory[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t } = useT();

  const [editing, setEditing] = useState<LedgerCategory | null | undefined>(undefined);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [nameBn, setNameBn] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const open = (row: LedgerCategory | null) => {
    setEditing(row);
    setCode(row?.code ?? '');
    setName(row?.name ?? '');
    setNameBn(row?.name_bn ?? '');
    setIsActive(row?.is_active ?? true);
    setFormError(null);
    setFieldErrors({});
  };

  const save = async () => {
    if (editing === undefined) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body = {
      code: code.trim().toUpperCase(),
      name: name.trim(),
      name_bn: nameBn.trim(),
      is_active: isActive,
    };
    try {
      if (editing) await apiClient.patch<LedgerCategory>(path, editing.id, body);
      else await apiClient.create<LedgerCategory>(path, body);
      setEditing(undefined);
      onChanged();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('The category could not be saved.')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <BaseModal isOpen onClose={onClose} title={title} maxWidth="lg">
        <div className="space-y-3">
          <button type="button" onClick={() => open(null)} className={`${btnPrimary} w-full justify-center`}>
            {t('Add a category')}
          </button>

          <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
            {rows.map((row) => (
              <li key={row.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span className="min-w-0">
                  <span className={`block truncate text-sm font-medium ${row.is_active ? 'text-gray-900' : 'text-gray-400'}`}>
                    {row.name_bn || row.name}
                  </span>
                  <span className="block truncate text-xs text-gray-500">
                    {row.code}
                    {row.is_system ? ` · ${t('Seeded')}` : ''}
                    {row.is_active ? '' : ` · ${t('Off')}`}
                  </span>
                </span>
                <button type="button" onClick={() => open(row)} className={`${btnSecondary} shrink-0`}>
                  {t('Edit')}
                </button>
              </li>
            ))}
          </ul>

          {rows.length === 0 && (
            <p className="rounded-lg bg-gray-50 px-3 py-3 text-sm text-gray-600">
              {t('No categories yet.')}
            </p>
          )}
        </div>
      </BaseModal>

      {editing !== undefined && (
        <BaseModal
          isOpen
          onClose={() => setEditing(undefined)}
          title={editing ? t('Edit category') : t('Add a category')}
          footer={
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setEditing(undefined)}
                className={`${btnSecondary} flex-1 justify-center`}
              >
                {t('Cancel')}
              </button>
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving || name.trim() === '' || code.trim() === ''}
                className={`${btnPrimary} flex-1 justify-center`}
              >
                {saving ? t('Saving…') : t('Save')}
              </button>
            </div>
          }
        >
          <div className="space-y-4">
            <FormError message={formError} />
            <FieldGrid>
              <Field label={t('Code')} required error={fieldErrors.code}>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  type="text"
                  className={inputCls}
                  placeholder="DON"
                />
              </Field>
              <Field label={t('Name')} required error={fieldErrors.name}>
                <input value={name} onChange={(e) => setName(e.target.value)} type="text" className={inputCls} />
              </Field>
              <Field label={t('Name in Bangla')} error={fieldErrors.name_bn}>
                <input value={nameBn} onChange={(e) => setNameBn(e.target.value)} type="text" className={inputCls} />
              </Field>
            </FieldGrid>

            <label className="flex min-h-[44px] items-center gap-3 rounded-lg border border-gray-100 px-3">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-5 w-5 rounded border-gray-300 text-blue-600"
              />
              <span className="text-sm text-gray-800">{t('Active')}</span>
            </label>

            {editing?.is_system && (
              <p className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
                {t('This is a seeded category. It can be switched off but not deleted — entries point at it.')}
              </p>
            )}
          </div>
        </BaseModal>
      )}
    </>
  );
}
