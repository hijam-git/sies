import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { formatBDT } from '../../lib/format';
import BaseModal from '../common/BaseModal';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import type { AcademicsData } from './shared';

/**
 * Classes — the frame everything else hangs off.
 *
 * A class belongs to one stream and one session, so both are required: "Class
 * 6" without a year is two different sets of children, and the routine, the
 * fees and the marks all point at the row rather than at the name.
 */

interface ClassDraft {
  stream: string;
  session: string;
  name: string;
  name_bn: string;
  level_order: string;
  capacity: string;
  class_teacher: string;
  monthly_fee: string;
  is_active: boolean;
}

function emptyDraft(session: number | null): ClassDraft {
  return {
    stream: '',
    session: session === null ? '' : String(session),
    name: '',
    name_bn: '',
    level_order: '',
    capacity: '0',
    class_teacher: '',
    monthly_fee: '0',
    is_active: true,
  };
}

export default function ClassesTab({ data }: { data: AcademicsData }) {
  const { t } = useT();
  const { can } = usePermissions();

  const [rows, setRows] = useState<AcademicClass[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  /* `null` is "hasn't chosen", `''` is "chose All sessions" — the two have to
   * be different, or clearing the filters would snap straight back to the
   * default and the All option could never be used. */
  const [sessionChoice, setSessionChoice] = useState<string | null>(null);
  const [streamFilter, setStreamFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<ClassDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('academics', 'create');
  const mayUpdate = can('academics', 'update');

  const currentSession = useMemo(
    () => data.sessions.find((s) => s.is_current)?.id ?? data.sessions[0]?.id ?? null,
    [data.sessions],
  );

  // A class list spanning every year an institution has run repeats "Class 6"
  // once per year; the current session is the only one anybody opens this for.
  const sessionFilter = sessionChoice ?? String(currentSession ?? '');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const query = new URLSearchParams({ page: String(page) });
      if (search.trim()) query.set('search', search.trim());
      if (sessionFilter) query.set('session', sessionFilter);
      if (streamFilter) query.set('stream', streamFilter);
      if (activeFilter) query.set('is_active', activeFilter);
      const data_ = await apiClient.list<AcademicClass>('/classes/', `?${query}`);
      setRows(data_.results);
      setTotal(data_.count);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the classes.')));
    } finally {
      setLoading(false);
    }
  }, [page, search, sessionFilter, streamFilter, activeFilter, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
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

  const streamName = useMemo(() => {
    const byId = new Map(data.streams.map((x) => [x.id, x]));
    return (id: number | null) => {
      if (id === null) return '—';
      const stream = byId.get(id);
      return stream ? stream.name_bn || stream.name : '—';
    };
  }, [data.streams]);

  const openCreate = () => {
    setEditingId(null);
    setDraft(emptyDraft(currentSession));
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (row: AcademicClass) => {
    setEditingId(row.id);
    setDraft({
      stream: row.stream === null ? '' : String(row.stream),
      session: String(row.session),
      name: row.name,
      name_bn: row.name_bn,
      level_order: String(row.level_order),
      capacity: String(row.capacity),
      class_teacher: row.class_teacher === null ? '' : String(row.class_teacher),
      monthly_fee: row.monthly_fee,
      is_active: row.is_active,
    });
    setFormError(null);
    setFieldErrors({});
  };

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});

    const body: Record<string, unknown> = {
      stream: draft.stream ? Number(draft.stream) : null,
      session: Number(draft.session),
      name: draft.name.trim(),
      name_bn: draft.name_bn.trim(),
      level_order: Number(draft.level_order || 0),
      capacity: Number(draft.capacity || 0),
      class_teacher: draft.class_teacher ? Number(draft.class_teacher) : null,
      // Sent as typed, never parsed into a JS number: money is a Decimal on the
      // server and a float here is a rounding error nobody can trace.
      monthly_fee: draft.monthly_fee.trim() || '0',
      is_active: draft.is_active,
    };

    try {
      if (editingId !== null) await apiClient.patch<AcademicClass>('/classes/', editingId, body);
      else await apiClient.create<AcademicClass>('/classes/', body);
      setDraft(null);
      await load();
      await data.reloadClasses();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this class.')));
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<AcademicClass>[] = [
    {
      key: 'name',
      label: t('Class'),
      primary: true,
      render: (c) => (
        <span className="block">
          <span className="block">{c.name_bn || c.name}</span>
          <span className="block text-xs text-gray-500">
            {streamName(c.stream)} · {c.year}
          </span>
        </span>
      ),
    },
    { key: 'level', label: t('Level order'), render: (c) => c.level_order },
    {
      key: 'capacity',
      label: t('Capacity'),
      render: (c) => (c.capacity > 0 ? c.capacity : '—'),
    },
    {
      key: 'sections',
      label: t('Sections'),
      hideOnNarrow: true,
      render: (c) => c.section_count ?? '—',
    },
    {
      key: 'teacher',
      label: t('Class teacher'),
      render: (c) => teacherName(c.class_teacher) ?? t('Not assigned'),
    },
    {
      key: 'fee',
      label: t('Monthly fee'),
      render: (c) => formatBDT(c.monthly_fee),
    },
    {
      key: 'status',
      label: t('Status'),
      render: (c) => (
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            c.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {c.is_active ? t('Active') : t('Inactive')}
        </span>
      ),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      headClass: 'px-4 py-3 text-right',
      render: (c) =>
        mayUpdate ? (
          <button type="button" onClick={() => openEdit(c)} className={btnSecondary}>
            {t('Edit')}
          </button>
        ) : null,
    },
  ];

  const filtering = !!(search || sessionFilter || streamFilter || activeFilter);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-gray-500">
          {t('A class belongs to one stream and one session — the same name in a new year is a new class.')}
        </p>
        {mayCreate && (
          <button type="button" onClick={openCreate} className={btnPrimary}>
            {t('Add class')}
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
            placeholder={t('Search by class name')}
            aria-label={t('Search by class name')}
            className={filterInputCls}
          />
        }
        active={filtering}
        onClear={() => {
          setSearch('');
          setSessionChoice('');
          setStreamFilter('');
          setActiveFilter('');
          setPage(1);
        }}
      >
        <select
          value={sessionFilter}
          onChange={(e) => {
            setSessionChoice(e.target.value);
            setPage(1);
          }}
          aria-label={t('Session')}
          className={filterSelectCls}
        >
          <option value="">{t('All sessions')}</option>
          {data.sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <select
          value={streamFilter}
          onChange={(e) => {
            setStreamFilter(e.target.value);
            setPage(1);
          }}
          aria-label={t('Stream')}
          className={filterSelectCls}
        >
          <option value="">{t('All streams')}</option>
          {data.streams.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name_bn || s.name}
            </option>
          ))}
        </select>
        <select
          value={activeFilter}
          onChange={(e) => {
            setActiveFilter(e.target.value);
            setPage(1);
          }}
          aria-label={t('Status')}
          className={filterSelectCls}
        >
          <option value="">{t('Active and inactive')}</option>
          <option value="true">{t('Active')}</option>
          <option value="false">{t('Inactive')}</option>
        </select>
      </FilterBar>

      {loadError && <FormError message={loadError} />}

      <ResponsiveTable
        columns={columns}
        rows={rows}
        rowKey={(c) => c.id}
        empty={loading ? t('Loading…') : t('No classes yet.')}
        footer={
          <Pagination total={total} page={page} onChange={setPage} pageSize={PAGE_SIZE} />
        }
      />

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId === null ? t('Add class') : t('Edit class')}
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
              <Field label={t('Stream')} error={fieldErrors.stream} required>
                <select
                  value={draft.stream}
                  onChange={(e) => setDraft({ ...draft, stream: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Choose a stream')}</option>
                  {data.streams.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name_bn || s.name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label={t('Session')} error={fieldErrors.session} required>
                <select
                  value={draft.session}
                  onChange={(e) => setDraft({ ...draft, session: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Choose a session')}</option>
                  {data.sessions.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </Field>

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

              <Field
                label={t('Level order')}
                hint={t('Where this class sits in the ladder — it is what promotion follows.')}
                error={fieldErrors.level_order}
                required
              >
                <input
                  type="number"
                  inputMode="numeric"
                  value={draft.level_order}
                  onChange={(e) => setDraft({ ...draft, level_order: e.target.value })}
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

              <Field label={t('Class teacher')} error={fieldErrors.class_teacher}>
                <select
                  value={draft.class_teacher}
                  onChange={(e) => setDraft({ ...draft, class_teacher: e.target.value })}
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

              <Field label={t('Monthly fee')} error={fieldErrors.monthly_fee}>
                <input
                  type="text"
                  inputMode="decimal"
                  value={draft.monthly_fee}
                  onChange={(e) => setDraft({ ...draft, monthly_fee: e.target.value })}
                  className={inputCls}
                />
              </Field>

              <FieldWide>
                <label className="flex min-h-[44px] items-center gap-3">
                  <input
                    type="checkbox"
                    checked={draft.is_active}
                    onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                    className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">{t('Active')}</span>
                </label>
              </FieldWide>
            </FieldGrid>
          </div>
        )}
      </BaseModal>
    </div>
  );
}
