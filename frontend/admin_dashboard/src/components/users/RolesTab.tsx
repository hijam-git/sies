import { useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { PermissionCatalog, Role } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';
import PermissionMatrix from './PermissionMatrix';

/**
 * Roles — the ten shipped presets and any the institution adds.
 *
 * A system preset's **name** is read-only, and the screen says why rather than
 * disabling the field silently: `seed_roles` refers to these by name, so a
 * renamed preset comes back as a second copy on the next deploy. Its matrix is
 * still the institution's to adjust, and a system role cannot be deleted at all
 * — retiring one is switching it off, because every user still on it points at
 * the row.
 *
 * Editing a preset moves everyone still ON it and leaves customised people
 * alone (`docs/02` §2.3), which is what makes it worth editing rather than
 * ticking forty boxes twice.
 */

/** `{fees: ['view','collect']}` → `['fees.view', 'fees.collect']`. */
function flatten(matrix: Record<string, string[]>): string[] {
  return Object.entries(matrix).flatMap(([resource, actions]) =>
    actions.map((action) => `${resource}.${action}`),
  );
}

/** And back, because that is the shape the API stores. */
function toMatrix(permissions: string[]): Record<string, string[]> {
  const matrix: Record<string, string[]> = {};
  for (const permission of permissions) {
    const [resource, action] = permission.split('.');
    if (!resource || !action) continue;
    (matrix[resource] ??= []).push(action);
  }
  return matrix;
}

export default function RolesTab({ catalog }: { catalog: PermissionCatalog | null }) {
  const { t } = useT();
  const { can } = usePermissions();

  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Role | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [nameBn, setNameBn] = useState('');
  const [permissions, setPermissions] = useState<string[]>([]);
  const [isActive, setIsActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('users', 'create');
  const mayUpdate = can('users', 'update');

  /** Bumped to ask for a fresh list. The fetch itself lives inside the effect
   *  so nothing sets state synchronously in an effect body, and `alive` stops a
   *  late answer writing into a screen the user has already left. */
  const [reloadToken, setReloadToken] = useState(0);
  const reload = () => setReloadToken((n) => n + 1);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      try {
        const data = await apiClient.listRoles();
        if (!alive) return;
        setRoles(data);
        setLoadError(null);
      } catch (err) {
        if (alive) setLoadError(apiErrorText(err, t, t('Could not load the roles.')));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void run();
    return () => {
      alive = false;
    };
  }, [reloadToken, t]);

  const openRole = (role: Role) => {
    setEditing(role);
    setCreating(false);
    setName(role.name);
    setNameBn(role.name_bn);
    setPermissions(role.permissions.length ? role.permissions : flatten(role.permission_matrix));
    setIsActive(role.is_active);
    setFormError(null);
    setFieldErrors({});
  };

  const openCreate = () => {
    setEditing(null);
    setCreating(true);
    setName('');
    setNameBn('');
    setPermissions([]);
    setIsActive(true);
    setFormError(null);
    setFieldErrors({});
  };

  const close = () => {
    setEditing(null);
    setCreating(false);
  };

  const save = async () => {
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    try {
      const body: Record<string, unknown> = {
        name_bn: nameBn.trim(),
        permission_matrix: toMatrix(permissions),
        is_active: isActive,
      };
      // A system preset's name is left out of the payload entirely rather than
      // sent unchanged: the serializer drops it anyway, and sending it would
      // suggest this screen could change it.
      if (!editing?.is_system) body.name = name.trim();

      if (editing) await apiClient.updateRole(editing.id, body);
      else await apiClient.createRole(body);
      close();
      reload();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this role.')));
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<Role>[] = [
    {
      key: 'name',
      label: t('Name'),
      primary: true,
      render: (r) => (
        <span className="block">
          <span className="flex flex-wrap items-center gap-2">
            <span>{r.name_bn || r.name}</span>
            {r.is_system && (
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                {t('System preset')}
              </span>
            )}
          </span>
          {r.name_bn && <span className="block text-xs text-gray-500">{r.name}</span>}
        </span>
      ),
    },
    {
      key: 'permissions',
      label: t('Permissions'),
      render: (r) => `${(r.permissions.length || flatten(r.permission_matrix).length)}`,
    },
    { key: 'users', label: t('People on it'), render: (r) => r.user_count },
    {
      key: 'status',
      label: t('Status'),
      render: (r) => (r.is_active ? t('Active') : t('Inactive')),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      render: (r) => (
        <button
          type="button"
          onClick={() => openRole(r)}
          className="tap rounded-lg px-3 text-sm font-medium text-blue-700 hover:bg-blue-50"
        >
          {mayUpdate ? t('Edit') : t('View')}
        </button>
      ),
    },
  ];

  const open = creating || editing !== null;
  // The name is fixed on a shipped preset; the matrix is not. `readOnly` on the
  // matrix therefore tracks the permission, not `is_system`.
  const matrixReadOnly = !mayUpdate;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-500">
          {t('A role ticks a set of boxes. The boxes are what gets enforced.')}
        </p>
        {mayCreate && (
          <button type="button" onClick={openCreate} className={`${btnPrimary} w-full sm:w-auto`}>
            {t('Add role')}
          </button>
        )}
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {loadError}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Loading...')}
        </div>
      ) : (
        <ResponsiveTable
          columns={columns}
          rows={roles}
          rowKey={(r) => r.id}
          empty={t('No roles yet.')}
        />
      )}

      <BaseModal
        isOpen={open && catalog !== null}
        onClose={close}
        title={creating ? t('Add role') : t('Edit role')}
        maxWidth="4xl"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={close} className={`${btnSecondary} flex-1`}>
              {mayUpdate ? t('Cancel') : t('Close')}
            </button>
            {mayUpdate && (
              <button
                type="button"
                onClick={() => void save()}
                className={`${btnPrimary} flex-1`}
                disabled={saving}
              >
                {saving ? t('Saving...') : t('Save')}
              </button>
            )}
          </div>
        }
      >
        {catalog && (
          <div className="space-y-4">
            <FormError message={formError} />

            {editing?.is_system && (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
                <p className="font-medium">{t('This is a system preset.')}</p>
                <p className="mt-1 leading-relaxed">
                  {t(
                    'Its name cannot change — the seed and every account on it refer to the preset by name — and it cannot be deleted while people are on it. You can still adjust its permissions, or switch it off to retire it.',
                  )}
                </p>
              </div>
            )}

            <FieldGrid>
              <Field label={t('Name (English)')} required error={fieldErrors.name}>
                <input
                  className={inputCls}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={Boolean(editing?.is_system) || !mayUpdate}
                  required
                />
              </Field>
              <Field label={t('Name (Bangla)')} error={fieldErrors.name_bn}>
                <input
                  className={inputCls}
                  lang="bn"
                  value={nameBn}
                  onChange={(e) => setNameBn(e.target.value)}
                  disabled={!mayUpdate}
                />
              </Field>
            </FieldGrid>

            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                className="h-5 w-5 rounded border-gray-300 text-blue-600"
                checked={isActive}
                disabled={!mayUpdate}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              <span className="text-sm font-medium text-gray-900">
                {t('This role can be assigned')}
              </span>
            </label>

            <PermissionMatrix
              catalog={catalog}
              selected={permissions}
              onChange={setPermissions}
              readOnly={matrixReadOnly}
              header={
                <p className="mb-3 text-sm text-gray-500">
                  {t(
                    'Changing these moves everyone still on this preset. People whose permissions have been customised are left alone.',
                  )}
                </p>
              }
            />
          </div>
        )}
      </BaseModal>
    </div>
  );
}
