import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Section } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import BaseModal from '../common/BaseModal';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls, btnRowAction } from '../common/styles';
import Picker from '../common/Picker';
import { preferredClassId, useOwnTeacherId } from '../../lib/defaults';
import { classLabel } from './shared';
import type { AcademicsData } from './shared';

/**
 * Sections, under one chosen class.
 *
 * Class-first rather than a flat list with a class column: a section is called
 * "ক" in nine different classes, so a list of forty rows named ক, খ, গ over and
 * over is unreadable however it is sorted.
 */

interface SectionDraft {
  name: string;
  name_bn: string;
  capacity: string;
  room: string;
  in_charge: string;
  is_active: boolean;
}

const EMPTY_DRAFT: SectionDraft = {
  name: '',
  name_bn: '',
  capacity: '0',
  room: '',
  in_charge: '',
  is_active: true,
};

export default function SectionsTab({ data }: { data: AcademicsData }) {
  const { t } = useT();
  const { can } = usePermissions();

  // The picker holds the CHOICE; the class in use falls back to the first one
  // so the tab is never an empty frame waiting for a decision the user has no
  // reason to think is required. Derived rather than written from an effect,
  // which would render once with nothing chosen and again with the default.
  const [classChoice, setClassChoice] = useState<string>('');
  const [rows, setRows] = useState<Section[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<SectionDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('academics', 'create');
  const mayUpdate = can('academics', 'update');
  const mayDelete = can('academics', 'delete');

  // A class teacher opening Sections is opening their own class's sections;
  // for anyone else the list's own order — latest year first — is the answer.
  const ownTeacherId = useOwnTeacherId(data.teachers);
  const classId = data.classes.some((c) => String(c.id) === classChoice)
    ? classChoice
    : preferredClassId(data.classes, ownTeacherId);

  /* The filter can change while the request is in the air, and the slower of
   * two answers wins by landing last — under the new heading. */
  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    if (!classId) {
      setRows([]);
      return;
    }
    setLoading(true);
    setLoadError(null);
    try {
      const data = await apiClient.listAll<Section>('/sections/', `?academic_class=${classId}`);
      if (!req.isCurrent(mine)) return;
      setRows(data);
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setLoadError(apiErrorText(err, t, t('Could not load the sections.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [classId, req, t]);

  // Deferred by a tick rather than called from the effect body: `load` sets
  // state synchronously, which during an effect cascades a render before the
  // first paint. The same shape the other list screens use.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  const teacherName = useMemo(() => {
    const byId = new Map(data.teachers.map((x) => [x.id, x]));
    return (id: number | null) => {
      if (id === null) return null;
      const teacher = byId.get(id);
      return teacher ? teacher.name_bn || teacher.name : null;
    };
  }, [data.teachers]);

  const openCreate = () => {
    setEditingId(null);
    setDraft({ ...EMPTY_DRAFT });
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (row: Section) => {
    setEditingId(row.id);
    setDraft({
      name: row.name,
      name_bn: row.name_bn,
      capacity: String(row.capacity),
      room: row.room,
      in_charge: row.in_charge === null ? '' : String(row.in_charge),
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
      name: draft.name.trim(),
      name_bn: draft.name_bn.trim(),
      capacity: Number(draft.capacity || 0),
      room: draft.room.trim(),
      in_charge: draft.in_charge ? Number(draft.in_charge) : null,
      is_active: draft.is_active,
    };
    try {
      if (editingId !== null) await apiClient.patch<Section>('/sections/', editingId, body);
      else await apiClient.create<Section>('/sections/', body);
      setDraft(null);
      await load();
      await data.reloadClasses();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this section.')));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row: Section) => {
    if (!window.confirm(t('Delete this section? Students already in it keep their enrolment.'))) return;
    try {
      await apiClient.destroy('/sections/', row.id);
      await load();
      await data.reloadClasses();
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not delete this section.')));
    }
  };

  const columns: Column<Section>[] = [
    { key: 'name', label: t('Section'), primary: true, render: (s) => s.name_bn || s.name },
    { key: 'capacity', label: t('Capacity'), render: (s) => (s.capacity > 0 ? s.capacity : '—') },
    { key: 'room', label: t('Room'), render: (s) => s.room || '—' },
    {
      key: 'in_charge',
      label: t('In charge'),
      render: (s) => teacherName(s.in_charge) ?? t('Not assigned'),
    },
    {
      key: 'status',
      label: t('Status'),
      render: (s) => (s.is_active ? t('Active') : t('Inactive')),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (s) => (
        <span className="inline-flex gap-2">
          {mayUpdate && (
            <button type="button" onClick={() => openEdit(s)} className={btnRowAction}>
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
    <div className="space-y-3">
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
            {t('Add section')}
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
              ? t('This class has no sections yet.')
              : t('Choose a class to see its sections.')
        }
      />

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId === null ? t('Add section') : t('Edit section')}
        maxWidth="lg"
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
          <div className="space-y-3">
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
              <Field label={t('Capacity')} error={fieldErrors.capacity}>
                <input
                  type="number"
                  inputMode="numeric"
                  value={draft.capacity}
                  onChange={(e) => setDraft({ ...draft, capacity: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Room')} error={fieldErrors.room}>
                <input
                  value={draft.room}
                  onChange={(e) => setDraft({ ...draft, room: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('In charge')} error={fieldErrors.in_charge}>
                <select
                  value={draft.in_charge}
                  onChange={(e) => setDraft({ ...draft, in_charge: e.target.value })}
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
