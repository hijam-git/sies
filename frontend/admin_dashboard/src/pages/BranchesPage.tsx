import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { Branch, Stream } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../lib/apiErrors';
import BaseModal from '../components/common/BaseModal';
import FilterBar, { filterInputCls, filterSelectCls } from '../components/common/FilterBar';
import Pagination, { PAGE_SIZE } from '../components/common/Pagination';
import ResponsiveTable from '../components/common/ResponsiveTable';
import type { Column } from '../components/common/ResponsiveTable';
import { btnPrimary, btnSecondary } from '../components/common/styles';
import BranchForm from '../components/settings/BranchForm';
import { TYPE_LABELS, draftFrom, draftToPayload, emptyDraft } from '../components/settings/branchDraft';
import type { BranchDraft } from '../components/settings/branchDraft';

/**
 * Institutions — the platform operator's own screen (`docs/08` D1).
 *
 * Two gates, not one. `branches.view` says the person may read institution
 * records at all, which a principal also holds for their own; `user.branch ===
 * null` says they are the operator of SIES rather than a customer of it. A
 * principal meeting this list would be reading another organisation's details.
 *
 * Creating one is a single transaction on the server: `create_branch` writes
 * the institution AND seeds its streams from `institution_type`. The success
 * state shows those streams rather than a bare "saved", because otherwise the
 * one visible consequence of choosing the type happens invisibly and the
 * operator's next question is whether it worked.
 */
export default function BranchesPage() {
  const { t } = useT();
  const { user } = useAuth();
  const { can, canView } = usePermissions();

  const [rows, setRows] = useState<Branch[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editing, setEditing] = useState<Branch | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<BranchDraft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  /** The institution just created and the streams the server seeded with it. */
  const [seeded, setSeeded] = useState<{ branch: Branch; streams: Stream[] } | null>(null);

  const isPlatformAdmin = user?.branch === null;
  const allowed = isPlatformAdmin && canView('branches');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const query = new URLSearchParams();
      query.set('page', String(page));
      if (search.trim()) query.set('search', search.trim());
      if (typeFilter) query.set('institution_type', typeFilter);
      if (activeFilter) query.set('is_active', activeFilter);
      const data = await apiClient.listBranches(`?${query.toString()}`);
      setRows(data.results);
      setTotal(data.count);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the institutions.')));
    } finally {
      setLoading(false);
    }
  }, [page, search, typeFilter, activeFilter, t]);

  useEffect(() => {
    if (!allowed) return;
    // Debounced, so typing into the search box is one request per pause rather
    // than one per keystroke against a list the operator scrolls anyway.
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [allowed, load]);

  if (!allowed) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Institutions')}</h1>
        <p className="mt-2 text-sm text-gray-500">
          {t('Only a platform administrator can see the list of institutions.')}
        </p>
      </div>
    );
  }

  const openCreate = () => {
    setDraft(emptyDraft());
    setFormError(null);
    setFieldErrors({});
    setCreating(true);
  };

  const openEdit = (branch: Branch) => {
    setDraft(draftFrom(branch));
    setFormError(null);
    setFieldErrors({});
    setEditing(branch);
  };

  const closeForm = () => {
    setCreating(false);
    setEditing(null);
  };

  const save = async () => {
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    try {
      if (editing) {
        await apiClient.updateBranch(editing.id, draftToPayload(draft, true));
        closeForm();
        await load();
      } else {
        const branch = await apiClient.createBranch(draftToPayload(draft, false));
        // A second request, because the create response is the branch alone.
        // The streams it seeded are the point of having chosen a type, so they
        // are read back and shown rather than left for the operator to go and
        // check on another screen.
        let streams: Stream[] = [];
        try {
          streams = await apiClient.listStreams(branch.id);
        } catch {
          // The institution exists either way; a failed follow-up read must not
          // read as a failed creation.
        }
        setCreating(false);
        setSeeded({ branch, streams });
        await load();
      }
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this institution.')));
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<Branch>[] = [
    {
      key: 'name',
      label: t('Name'),
      primary: true,
      render: (b) => (
        <span className="block">
          <span className="block">{b.name_bn || b.name}</span>
          {b.name_bn && <span className="block text-xs text-gray-500">{b.name}</span>}
        </span>
      ),
    },
    { key: 'code', label: t('Code'), render: (b) => <span className="font-mono">{b.code}</span> },
    {
      key: 'type',
      label: t('Institution type'),
      render: (b) => t(TYPE_LABELS[b.institution_type]),
    },
    {
      key: 'district',
      label: t('District'),
      hideOnNarrow: true,
      render: (b) => b.district || '—',
    },
    {
      key: 'status',
      label: t('Status'),
      render: (b) => (
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            b.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {b.is_active ? t('Active') : t('Inactive')}
        </span>
      ),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      render: (b) =>
        can('branches', 'update') ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              openEdit(b);
            }}
            className="tap rounded-lg px-3 text-sm font-medium text-blue-700 hover:bg-blue-50"
          >
            {t('Edit')}
          </button>
        ) : null,
    },
  ];

  const filtering = Boolean(search || typeFilter || activeFilter);

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Institutions')}</h1>
        </div>
        {can('branches', 'create') && (
          <button type="button" onClick={openCreate} className={`${btnPrimary} w-full sm:w-auto`}>
            {t('Add institution')}
          </button>
        )}
      </header>

      <FilterBar
        active={filtering}
        onClear={() => {
          setSearch('');
          setTypeFilter('');
          setActiveFilter('');
          setPage(1);
        }}
        search={
          <input
            className={filterInputCls}
            placeholder={t('Search by name, code or district')}
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
          aria-label={t('Institution type')}
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">{t('All types')}</option>
          {(Object.keys(TYPE_LABELS) as (keyof typeof TYPE_LABELS)[]).map((type) => (
            <option key={type} value={type}>
              {t(TYPE_LABELS[type])}
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
          rowKey={(b) => b.id}
          onRowClick={can('branches', 'update') ? openEdit : undefined}
          empty={t('No institutions yet.')}
          footer={
            <Pagination total={total} page={page} onChange={setPage} pageSize={PAGE_SIZE} />
          }
        />
      )}

      <BaseModal
        isOpen={creating || editing !== null}
        onClose={closeForm}
        title={editing ? t('Edit institution') : t('Add institution')}
        maxWidth="2xl"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={closeForm} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            {/* Submits the form by id rather than calling save() directly, so
                the browser's own required-field validation still runs. */}
            <button type="submit" form="branch-form" className={`${btnPrimary} flex-1`} disabled={saving}>
              {saving ? t('Saving...') : editing ? t('Save Changes') : t('Create')}
            </button>
          </div>
        }
      >
        <BranchForm
          draft={draft}
          setDraft={setDraft}
          onSubmit={() => void save()}
          onCancel={closeForm}
          saving={saving}
          formError={formError}
          fieldErrors={fieldErrors}
          mode={editing ? 'edit' : 'create'}
        />
      </BaseModal>

      <BaseModal
        isOpen={seeded !== null}
        onClose={() => setSeeded(null)}
        title={t('Institution created')}
        footer={
          <button
            type="button"
            onClick={() => setSeeded(null)}
            className={`${btnPrimary} w-full`}
          >
            {t('Done')}
          </button>
        }
      >
        {seeded && (
          <div className="space-y-4">
            <p className="text-sm text-gray-700">
              <span className="font-semibold">{seeded.branch.name_bn || seeded.branch.name}</span>
              {' · '}
              <span className="font-mono">{seeded.branch.code}</span>
            </p>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
              <p className="text-sm font-medium text-emerald-900">
                {t('Streams seeded from the institution type')}
              </p>
              {seeded.streams.length > 0 ? (
                <ul className="mt-2 space-y-1">
                  {seeded.streams.map((s) => (
                    <li key={s.id} className="text-sm text-emerald-800">
                      {s.name_bn || s.name}{' '}
                      <span className="font-mono text-xs text-emerald-700">({s.code})</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-emerald-800">
                  {t('No streams were seeded. Add them under Settings.')}
                </p>
              )}
            </div>
            <p className="text-sm text-gray-500">
              {t(
                'Rename these to the institution’s own words under Settings, then open its first academic year.',
              )}
            </p>
          </div>
        )}
      </BaseModal>
    </div>
  );
}
