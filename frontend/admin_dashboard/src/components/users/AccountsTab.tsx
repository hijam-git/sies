import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Branch, PermissionCatalog, Role, User, UserType } from '../../lib/api';
import { useAuth, usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { normalizeBdPhone, phoneInputValue } from '../../lib/normalizeBdPhone';
import { formatDhakaDateTime } from '../../lib/timezone';
import BaseModal from '../common/BaseModal';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import ResponsiveTable from '../common/ResponsiveTable';
import StatusDot from '../common/StatusDot';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import PermissionMatrix from './PermissionMatrix';

/**
 * Staff accounts (`docs/02` §1).
 *
 * The phone is the login and there is no other — so it is canonicalised with
 * `normalizeBdPhone` before it is sent, exactly as the login box does. A
 * principal who typed `+8801712…` and a clerk who later types `01712-345678`
 * must reach the same account; compared as raw text they are two people.
 */

/* The types this form can MAKE. Not `platform_accountant`, which the server
   has no such type for — that is the Platform Accountant role on a platform
   account. Not `student`: a student's login is switched on from their own
   record (Students → enable login), which links the two; one made here would
   belong to nobody. Both still display on an existing row (USER_TYPE_LABELS). */
const USER_TYPES: UserType[] = ['platform_admin', 'principal', 'accountant', 'teacher', 'employee'];

/* Presets that describe work across every institution — only meaningful on a
   platform account. The server refuses them anywhere else (accounts.serializers). */
const PLATFORM_ROLES = new Set(['Platform Admin', 'Platform Accountant']);

const USER_TYPE_LABELS: Record<UserType, string> = {
  platform_admin: 'Platform admin',
  platform_accountant: 'Platform accountant',
  principal: 'Principal',
  accountant: 'Accountant',
  teacher: 'Teacher',
  employee: 'Employee',
  student: 'Student',
};

interface UserDraft {
  phone: string;
  name: string;
  name_bn: string;
  email: string;
  /** '' until chosen — there is no safe default. The old default, Teacher,
   *  is how an account got made that could add students and list none. */
  user_type: UserType | '';
  branch: string;
  role: string;
  language: 'bn' | 'en';
  password: string;
  must_change_password: boolean;
}

function emptyUserDraft(defaultBranch: number | null): UserDraft {
  return {
    phone: '',
    name: '',
    name_bn: '',
    email: '',
    user_type: '',
    branch: defaultBranch === null ? '' : String(defaultBranch),
    role: '',
    language: 'bn',
    password: '',
    must_change_password: true,
  };
}

export default function AccountsTab({ catalog }: { catalog: PermissionCatalog | null }) {
  const { t } = useT();
  const { user: me, activeBranchId } = useAuth();
  const { can } = usePermissions();

  const [rows, setRows] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [roles, setRoles] = useState<Role[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);

  const [draft, setDraft] = useState<UserDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [permissionTarget, setPermissionTarget] = useState<User | null>(null);
  const [permissionDraft, setPermissionDraft] = useState<string[]>([]);
  /** Whether the boxes on screen came from the person's own list or from their
   *  role's preset. The difference is the whole of `docs/02` §2.3. */
  const [wasCustomised, setWasCustomised] = useState(false);

  const isPlatformAdmin = me?.branch === null;
  const mayCreate = can('users', 'create');
  const mayUpdate = can('users', 'update');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const query = new URLSearchParams();
      query.set('page', String(page));
      if (search.trim()) query.set('search', search.trim());
      if (typeFilter) query.set('user_type', typeFilter);
      if (roleFilter) query.set('role', roleFilter);
      if (activeFilter) query.set('is_active', activeFilter);
      const data = await apiClient.listUsers(`?${query.toString()}`);
      setRows(data.results);
      setTotal(data.count);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the accounts.')));
    } finally {
      setLoading(false);
    }
  }, [page, search, typeFilter, roleFilter, activeFilter, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    void apiClient.listRoles().then(setRoles).catch(() => setRoles([]));
    // Only a platform admin picks an institution for a new account; everyone
    // else's is stamped from their own, so the list is a request they never
    // need to make.
    if (isPlatformAdmin) {
      void apiClient.getBranches().then(setBranches).catch(() => setBranches([]));
    }
  }, [isPlatformAdmin]);

  const roleName = useMemo(() => {
    const byId = new Map(roles.map((r) => [r.id, r]));
    return (id: number | null) => {
      if (id === null) return null;
      const role = byId.get(id);
      return role ? role.name_bn || role.name : null;
    };
  }, [roles]);

  const openCreate = () => {
    setEditingId(null);
    setDraft(emptyUserDraft(me?.branch ?? activeBranchId));
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (row: User) => {
    setEditingId(row.id);
    setDraft({
      phone: row.phone,
      name: row.name,
      name_bn: row.name_bn,
      email: row.email ?? '',
      user_type: row.user_type,
      branch: row.branch === null ? '' : String(row.branch),
      role: row.role === null ? '' : String(row.role),
      language: row.language,
      password: '',
      must_change_password: row.must_change_password ?? false,
    });
    setFormError(null);
    setFieldErrors({});
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});

    if (!draft.user_type) {
      setFieldErrors({ user_type: t('Choose what kind of account this is.') });
      setSaving(false);
      return;
    }

    const canonical = normalizeBdPhone(draft.phone);
    if (!canonical) {
      setFieldErrors({ phone: t('Enter an 11-digit mobile number, e.g. 01712345678.') });
      setSaving(false);
      return;
    }

    const body: Record<string, unknown> = {
      phone: canonical,
      name: draft.name.trim(),
      name_bn: draft.name_bn.trim(),
      email: draft.email.trim(),
      user_type: draft.user_type,
      role: draft.role ? Number(draft.role) : null,
      language: draft.language,
      must_change_password: draft.must_change_password,
    };
    if (draft.password) body.password = draft.password;

    try {
      if (editingId !== null) {
        await apiClient.updateUser(editingId, body);
      } else {
        // `branch` is a request parameter, never a body field: the server
        // stamps it, so a branch id in the payload would be ignored anyway.
        const branch = draft.user_type === 'platform_admin'
          ? null
          : Number(draft.branch || me?.branch || activeBranchId || 0) || null;
        await apiClient.createUser(body, branch);
      }
      setDraft(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this account.')));
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (row: User) => {
    try {
      await apiClient.updateUser(row.id, { is_active: !row.is_active });
      await load();
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not change this account.')));
    }
  };

  const openPermissions = (row: User) => {
    const customised = row.permissions.length > 0;
    setWasCustomised(customised);
    // Either way the boxes start ticked at what the SERVER currently enforces —
    // the person's own list, or their preset expanded. Saving turns whatever is
    // on screen into their own list, which is what `docs/02` §2.3 says happens.
    setPermissionDraft(customised ? [...row.permissions] : [...(row.effective_permissions ?? [])]);
    setPermissionTarget(row);
  };

  const savePermissions = async () => {
    if (!permissionTarget) return;
    setSaving(true);
    setFormError(null);
    try {
      await apiClient.setUserPermissions(permissionTarget.id, permissionDraft);
      setPermissionTarget(null);
      await load();
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not save these permissions.')));
    } finally {
      setSaving(false);
    }
  };

  /** Back to the role's preset — an empty list, not every box re-ticked. Only
   *  an empty list restores the "follows the preset" state, so that changing the
   *  preset later moves this person with it. */
  const resetToPreset = async () => {
    if (!permissionTarget) return;
    setSaving(true);
    try {
      await apiClient.setUserPermissions(permissionTarget.id, []);
      setPermissionTarget(null);
      await load();
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not save these permissions.')));
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<User>[] = [
    {
      key: 'name',
      label: t('Name'),
      primary: true,
      render: (u) => (
        // One line: the phone after the name, not under it (see TeachersTab).
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate">{u.name_bn || u.name}</span>
          <span className="shrink-0 font-mono text-xs text-gray-400">{u.phone}</span>
        </span>
      ),
    },
    {
      key: 'type',
      label: t('User type'),
      render: (u) => (
        <span className="inline-flex flex-wrap items-center gap-1.5">
          {t(USER_TYPE_LABELS[u.user_type] ?? u.user_type)}
          {u.user_type === 'teacher' && u.has_teacher_profile === false && (
            <span
              className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800"
              title={t('Link this login on the teacher’s record (Teachers → edit). Until then it sees no classes or students.')}
            >
              {t('Not linked to a teacher')}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'role',
      label: t('Role'),
      render: (u) => roleName(u.role) ?? t('No role'),
    },
    {
      key: 'permissions',
      label: t('Permissions'),
      hideOnNarrow: true,
      render: (u) =>
        u.permissions.length > 0 ? (
          <StatusDot tone="amber" label={t('Customised')} />
        ) : (
          <span className="text-xs text-gray-500">{t('Follows the preset')}</span>
        ),
    },
    {
      key: 'last_login',
      label: t('Last login'),
      hideOnNarrow: true,
      render: (u) => (u.last_login ? formatDhakaDateTime(u.last_login) : '—'),
    },
    {
      key: 'status',
      label: t('Status'),
      render: (u) => (
        <StatusDot
          tone={u.is_active ? 'green' : 'gray'}
          label={u.is_active ? t('Active') : t('Inactive')}
        />
      ),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-3 py-2 text-right',
      render: (u) => (
        <span className="flex flex-wrap items-center justify-end gap-1">
          {mayUpdate && (
            <button
              type="button"
              onClick={() => openEdit(u)}
              className="tap md:-my-2 rounded-lg px-3 text-sm font-medium text-blue-700 hover:bg-blue-50"
            >
              {t('Edit')}
            </button>
          )}
          {mayUpdate && catalog && (
            <button
              type="button"
              onClick={() => openPermissions(u)}
              className="tap md:-my-2 rounded-lg px-3 text-sm font-medium text-gray-700 hover:bg-gray-100"
            >
              {t('Permissions')}
            </button>
          )}
          {mayUpdate && u.id !== me?.id && (
            <button
              type="button"
              onClick={() => void toggleActive(u)}
              className={`tap rounded-lg px-3 text-sm font-medium ${
                u.is_active ? 'text-red-700 hover:bg-red-50' : 'text-emerald-700 hover:bg-emerald-50'
              }`}
            >
              {u.is_active ? t('Deactivate') : t('Reactivate')}
            </button>
          )}
        </span>
      ),
    },
  ];

  const filtering = Boolean(search || typeFilter || roleFilter || activeFilter);

  return (
    <div className="space-y-3">
      <FilterBar
        actions={
          mayCreate && (
            <button type="button" onClick={openCreate} className={btnPrimary}>
              {t('Add account')}
            </button>
          )
        }
        active={filtering}
        onClear={() => {
          setSearch('');
          setTypeFilter('');
          setRoleFilter('');
          setActiveFilter('');
          setPage(1);
        }}
        search={
          <input
            className={filterInputCls}
            placeholder={t('Search by name or phone')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        }
      >
        <select
          className={filterSelectCls}
          aria-label={t('User type')}
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t('All types')}</option>
          {USER_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(USER_TYPE_LABELS[type])}
            </option>
          ))}
        </select>
        <select
          className={filterSelectCls}
          aria-label={t('Role')}
          value={roleFilter}
          onChange={(e) => {
            setRoleFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t('All roles')}</option>
          {roles.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name_bn || role.name}
            </option>
          ))}
        </select>
        <select
          className={filterSelectCls}
          aria-label={t('Status')}
          value={activeFilter}
          onChange={(e) => {
            setActiveFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t('All')}</option>
          <option value="true">{t('Active')}</option>
          <option value="false">{t('Inactive')}</option>
        </select>
      </FilterBar>

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
          rows={rows}
          rowKey={(u) => u.id}
          empty={t('No accounts yet.')}
          footer={<Pagination total={total} page={page} onChange={setPage} pageSize={PAGE_SIZE} />}
        />
      )}

      {/* ── The account form ───────────────────────────────────────────── */}
      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId !== null ? t('Edit account') : t('Add account')}
        maxWidth="2xl"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button type="submit" form="user-form" className={`${btnPrimary} flex-1`} disabled={saving}>
              {saving ? t('Saving...') : t('Save')}
            </button>
          </div>
        }
      >
        {draft && (
          <form
            id="user-form"
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <FormError message={formError} />
            <FieldGrid>
              <Field
                label={t('Phone')}
                required
                hint={t('11 digits. This is the login.')}
                error={fieldErrors.phone}
              >
                <input
                  className={`${inputCls} font-mono`}
                  value={draft.phone}
                  onChange={(e) => setDraft({ ...draft, phone: phoneInputValue(e.target.value) })}
                  inputMode="numeric"
                  autoComplete="off"
                  required
                />
              </Field>

              <Field
                label={t('User type')}
                required
                error={fieldErrors.user_type}
                hint={
                  draft.user_type === 'teacher'
                    ? t('Link this login on the teacher’s record (Teachers → edit). Until then it sees no classes or students.')
                    : draft.user_type === 'platform_admin'
                      ? t('Every institution. What they may do comes from the role — e.g. Platform Accountant for money only.')
                      : undefined
                }
              >
                <select
                  className={selectCls}
                  value={draft.user_type}
                  onChange={(e) => {
                    const userType = e.target.value as UserType | '';
                    // A platform role left selected after switching to an
                    // institution type would be refused on save; clear it here.
                    const role = roles.find((r) => String(r.id) === draft.role);
                    const keepRole = userType === 'platform_admin' || !role || !PLATFORM_ROLES.has(role.name);
                    setDraft({ ...draft, user_type: userType, role: keepRole ? draft.role : '' });
                  }}
                  required
                >
                  <option value="">{t('Choose one')}</option>
                  {(editingId !== null && !USER_TYPES.includes(draft.user_type as UserType)
                    ? [...USER_TYPES, draft.user_type as UserType]
                    : USER_TYPES
                  ).map((type) => (
                    <option key={type} value={type}>
                      {t(USER_TYPE_LABELS[type])}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label={t('Name (English)')} required error={fieldErrors.name}>
                <input
                  className={inputCls}
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  required
                />
              </Field>

              <Field label={t('Name (Bangla)')} error={fieldErrors.name_bn}>
                <input
                  className={inputCls}
                  lang="bn"
                  value={draft.name_bn}
                  onChange={(e) => setDraft({ ...draft, name_bn: e.target.value })}
                />
              </Field>

              {isPlatformAdmin && editingId === null && draft.user_type !== 'platform_admin' && (
                <Field
                  label={t('Institution')}
                  required
                  hint={t('Which institution this account belongs to')}
                  error={fieldErrors.branch}
                >
                  <select
                    className={selectCls}
                    value={draft.branch}
                    onChange={(e) => setDraft({ ...draft, branch: e.target.value })}
                    required
                  >
                    <option value="">{t('Choose one')}</option>
                    {branches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name_bn || b.name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}

              <Field
                label={t('Role')}
                hint={t('A starting point for their permissions, not a cage')}
                error={fieldErrors.role}
              >
                <select
                  className={selectCls}
                  value={draft.role}
                  onChange={(e) => setDraft({ ...draft, role: e.target.value })}
                >
                  <option value="">{t('No role')}</option>
                  {roles
                    .filter((role) => draft.user_type === 'platform_admin' || !PLATFORM_ROLES.has(role.name))
                    .map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name_bn || role.name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label={t('Language')} error={fieldErrors.language}>
                <select
                  className={selectCls}
                  value={draft.language}
                  onChange={(e) => setDraft({ ...draft, language: e.target.value as 'bn' | 'en' })}
                >
                  <option value="bn">বাংলা</option>
                  <option value="en">English</option>
                </select>
              </Field>

              <Field
                label={editingId === null ? t('Password') : t('New password')}
                hint={t('Leave blank to set it later, in person.')}
                error={fieldErrors.password}
              >
                <input
                  className={inputCls}
                  type="password"
                  value={draft.password}
                  onChange={(e) => setDraft({ ...draft, password: e.target.value })}
                  autoComplete="new-password"
                />
              </Field>
            </FieldGrid>

            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                className="mt-1 h-5 w-5 shrink-0 rounded border-gray-300 text-blue-600"
                checked={draft.must_change_password}
                onChange={(e) => setDraft({ ...draft, must_change_password: e.target.checked })}
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  {t('Make them change this password at first sign-in')}
                </span>
                <span className="mt-0.5 block text-xs text-gray-500">
                  {t('A password said out loud in order to hand it over must not stay the password.')}
                </span>
              </span>
            </label>
          </form>
        )}
      </BaseModal>

      {/* ── The permission screen ──────────────────────────────────────── */}
      <BaseModal
        isOpen={permissionTarget !== null && catalog !== null}
        onClose={() => setPermissionTarget(null)}
        title={t('Permissions')}
        maxWidth="4xl"
        footer={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setPermissionTarget(null)}
              className={`${btnSecondary} flex-1`}
            >
              {t('Cancel')}
            </button>
            {wasCustomised && (
              <button
                type="button"
                onClick={() => void resetToPreset()}
                className={`${btnSecondary} flex-1`}
                disabled={saving}
              >
                {t('Back to the preset')}
              </button>
            )}
            <button
              type="button"
              onClick={() => void savePermissions()}
              className={`${btnPrimary} flex-1`}
              disabled={saving}
            >
              {saving ? t('Saving...') : t('Save')}
            </button>
          </div>
        }
      >
        {permissionTarget && catalog && (
          <PermissionMatrix
            catalog={catalog}
            selected={permissionDraft}
            onChange={setPermissionDraft}
            header={
              <div className="mb-4 space-y-3">
                <p className="text-sm font-medium text-gray-900">
                  {permissionTarget.name_bn || permissionTarget.name}
                  <span className="ml-2 font-mono text-xs text-gray-500">
                    {permissionTarget.phone}
                  </span>
                </p>
                <div
                  className={`rounded-lg border p-3 text-sm ${
                    wasCustomised
                      ? 'border-amber-200 bg-amber-50 text-amber-900'
                      : 'border-blue-200 bg-blue-50 text-blue-900'
                  }`}
                >
                  <p className="font-medium">
                    {wasCustomised
                      ? t('This person has their own permission list.')
                      : t('This person follows their role’s preset.')}
                    {roleName(permissionTarget.role)
                      ? ` · ${roleName(permissionTarget.role)}`
                      : ''}
                  </p>
                  <p className="mt-1 leading-relaxed">
                    {t(
                      'A preset is a starting point. Once you save here, this list is the whole truth for this person — it is not merged with the preset, and changing the preset later will no longer move them. Use “Back to the preset” to undo that.',
                    )}
                  </p>
                </div>

                {/* Start from a preset, then adjust. This only TICKS BOXES — it
                    does not change the person's role, because the role is what
                    they are and this list is what they may do. */}
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-gray-700">
                    {t('Start from a preset')}
                  </span>
                  <select
                    className={selectCls}
                    value=""
                    onChange={(e) => {
                      const preset = catalog.presets.find((p) => p.name === e.target.value);
                      if (preset) setPermissionDraft([...preset.permissions]);
                    }}
                  >
                    <option value="">{t('Choose one')}</option>
                    {catalog.presets.map((preset) => (
                      <option key={preset.name} value={preset.name}>
                        {preset.name_bn || preset.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            }
          />
        )}
      </BaseModal>
    </div>
  );
}
