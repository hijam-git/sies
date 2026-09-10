import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Employee } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { formatDhakaDate } from '../../lib/timezone';
import BaseModal from '../common/BaseModal';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';
import PersonFields from './PersonFields';
import { EMPLOYMENT_STATUSES, EMPTY_PERSON, personBody, personDraftFrom } from './shared';
import type { PersonDraft } from './shared';

/**
 * Non-teaching staff — the office, the kitchen, the night guard.
 *
 * Its own resource and its own screen because an office manager who maintains
 * this roster has no business seeing what the teachers earn (`docs/02` §2.1).
 * Department and duty shift are free text on purpose: every institution names
 * them differently and a fixed list would fit none of them.
 */

interface EmployeeDraft extends PersonDraft {
  department: string;
  duty_shift: string;
}

const EMPTY_EMPLOYEE: EmployeeDraft = { ...EMPTY_PERSON, department: '', duty_shift: '' };

export default function EmployeesTab() {
  const { t } = useT();
  const { can } = usePermissions();

  const [rows, setRows] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  // Serving staff, matching `StudentsTab`'s enrolled-students default. A list
  // that mixes resigned and transferred people into today's staff has to be
  // filtered before it can be read, every single time.
  const [statusFilter, setStatusFilter] = useState('active');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<EmployeeDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('employees', 'create');
  const mayUpdate = can('employees', 'update');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const query = new URLSearchParams({ page: String(page) });
      if (search.trim()) query.set('search', search.trim());
      if (statusFilter) query.set('employment_status', statusFilter);
      const data = await apiClient.list<Employee>('/employees/', `?${query}`);
      setRows(data.results);
      setTotal(data.count);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the employees.')));
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setDraft({ ...EMPTY_EMPLOYEE });
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (row: Employee) => {
    setEditingId(row.id);
    setDraft({ ...personDraftFrom(row), department: row.department, duty_shift: row.duty_shift });
    setFormError(null);
    setFieldErrors({});
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      ...personBody(draft),
      department: draft.department.trim(),
      duty_shift: draft.duty_shift.trim(),
    };
    try {
      if (editingId !== null) await apiClient.patch<Employee>('/employees/', editingId, body);
      else await apiClient.create<Employee>('/employees/', body);
      setDraft(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this employee.')));
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<Employee>[] = [
    {
      key: 'name',
      label: t('Employee'),
      primary: true,
      render: (x) => (
        <span className="block">
          <span className="block">{x.name_bn || x.name}</span>
          <span className="block font-mono text-xs text-gray-500">{x.employee_id}</span>
        </span>
      ),
    },
    { key: 'designation', label: t('Designation'), render: (x) => x.designation || '—' },
    { key: 'department', label: t('Department'), render: (x) => x.department || '—' },
    { key: 'shift', label: t('Duty shift'), render: (x) => x.duty_shift || '—' },
    {
      key: 'joining',
      label: t('Joining date'),
      hideOnNarrow: true,
      render: (x) => (x.joining_date ? formatDhakaDate(x.joining_date) : '—'),
    },
    {
      key: 'status',
      label: t('Status'),
      render: (x) => (
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            x.employment_status === 'active'
              ? 'bg-emerald-100 text-emerald-800'
              : 'bg-gray-100 text-gray-600'
          }`}
        >
          {x.employment_status_display || x.employment_status}
        </span>
      ),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      headClass: 'px-4 py-3 text-right',
      render: (x) =>
        mayUpdate ? (
          <button type="button" onClick={() => openEdit(x)} className={btnSecondary}>
            {t('Edit')}
          </button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {mayCreate && (
          <button type="button" onClick={openCreate} className={btnPrimary}>
            {t('Add employee')}
          </button>
        )}
      </div>

      <FilterBar
        search={
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder={t('Search by name, ID or department')}
            aria-label={t('Search by name, ID or department')}
            className={filterInputCls}
          />
        }
        active={!!(search || statusFilter)}
        onClear={() => {
          setSearch('');
          setStatusFilter('');
          setPage(1);
        }}
      >
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          aria-label={t('Employment status')}
          className={filterSelectCls}
        >
          <option value="">{t('Every status')}</option>
          {EMPLOYMENT_STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {t(s.label)}
            </option>
          ))}
        </select>
      </FilterBar>

      {loadError && <FormError message={loadError} />}

      <ResponsiveTable
        columns={columns}
        rows={rows}
        rowKey={(x) => x.id}
        empty={loading ? t('Loading…') : t('No employees yet.')}
        footer={<Pagination total={total} page={page} onChange={setPage} pageSize={PAGE_SIZE} />}
      />

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId === null ? t('Add employee') : t('Edit employee')}
        maxWidth="4xl"
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
          <div className="space-y-5">
            <FormError message={formError} />
            <PersonFields draft={draft} onChange={(next) => setDraft({ ...draft, ...next })} errors={fieldErrors} />
            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">{t('Duty')}</h3>
              <FieldGrid>
                <Field label={t('Department')} error={fieldErrors.department}>
                  <input
                    value={draft.department}
                    onChange={(e) => setDraft({ ...draft, department: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Duty shift')} error={fieldErrors.duty_shift}>
                  <input
                    value={draft.duty_shift}
                    onChange={(e) => setDraft({ ...draft, duty_shift: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              </FieldGrid>
            </section>
          </div>
        )}
      </BaseModal>
    </div>
  );
}
