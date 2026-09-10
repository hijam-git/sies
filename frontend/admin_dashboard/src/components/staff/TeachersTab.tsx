import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Stream, Teacher, TeacherQualification } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { formatDhakaDate } from '../../lib/timezone';
import BaseModal from '../common/BaseModal';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';
import PersonFields from './PersonFields';
import { EMPLOYMENT_STATUSES, EMPTY_PERSON, personBody, personDraftFrom } from './shared';
import type { PersonDraft } from './shared';

/** Teaching staff. Separate from employees by design (`docs/08` D5): a teacher
 *  has streams, qualifications and a weekly period ceiling; a cook has none of
 *  them, and one table with half its columns always blank serves neither. */

interface TeacherDraft extends PersonDraft {
  streams: number[];
  is_class_teacher: boolean;
  specialization: string;
  max_weekly_periods: string;
}

const EMPTY_TEACHER: TeacherDraft = {
  ...EMPTY_PERSON,
  streams: [],
  is_class_teacher: false,
  specialization: '',
  max_weekly_periods: '',
};

interface QualificationDraft {
  degree: string;
  institution: string;
  year: string;
  result: string;
}

const EMPTY_QUALIFICATION: QualificationDraft = { degree: '', institution: '', year: '', result: '' };

export default function TeachersTab({ streams }: { streams: Stream[] }) {
  const { t } = useT();
  const { can } = usePermissions();

  const [rows, setRows] = useState<Teacher[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  // Serving staff, matching `StudentsTab`'s enrolled-students default. A list
  // that mixes resigned and transferred people into today's staff has to be
  // filtered before it can be read, every single time.
  const [statusFilter, setStatusFilter] = useState('active');
  const [streamFilter, setStreamFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<TeacherDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [qualTarget, setQualTarget] = useState<Teacher | null>(null);
  const [qualRows, setQualRows] = useState<TeacherQualification[]>([]);
  const [qualDraft, setQualDraft] = useState<QualificationDraft>(EMPTY_QUALIFICATION);
  const [qualError, setQualError] = useState<string | null>(null);

  const mayCreate = can('teachers', 'create');
  const mayUpdate = can('teachers', 'update');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const query = new URLSearchParams({ page: String(page) });
      if (search.trim()) query.set('search', search.trim());
      if (statusFilter) query.set('employment_status', statusFilter);
      if (streamFilter) query.set('streams', streamFilter);
      const data = await apiClient.list<Teacher>('/teachers/', `?${query}`);
      setRows(data.results);
      setTotal(data.count);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the teachers.')));
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter, streamFilter, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const streamNames = useMemo(() => {
    const byId = new Map(streams.map((s) => [s.id, s]));
    return (ids: number[]) =>
      ids
        .map((id) => byId.get(id))
        .filter((s): s is Stream => !!s)
        .map((s) => s.name_bn || s.name)
        .join(', ');
  }, [streams]);

  const openCreate = () => {
    setEditingId(null);
    setDraft({ ...EMPTY_TEACHER });
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (row: Teacher) => {
    setEditingId(row.id);
    setDraft({
      ...personDraftFrom(row),
      streams: [...row.streams],
      is_class_teacher: row.is_class_teacher,
      specialization: row.specialization,
      max_weekly_periods: row.max_weekly_periods === null ? '' : String(row.max_weekly_periods),
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
      ...personBody(draft),
      streams: draft.streams,
      is_class_teacher: draft.is_class_teacher,
      specialization: draft.specialization.trim(),
      max_weekly_periods: draft.max_weekly_periods ? Number(draft.max_weekly_periods) : null,
    };
    try {
      if (editingId !== null) await apiClient.patch<Teacher>('/teachers/', editingId, body);
      else await apiClient.create<Teacher>('/teachers/', body);
      setDraft(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this teacher.')));
    } finally {
      setSaving(false);
    }
  };

  const openQualifications = async (row: Teacher) => {
    setQualTarget(row);
    setQualDraft(EMPTY_QUALIFICATION);
    setQualError(null);
    // The list travels on the teacher row already, but it is re-read here so an
    // addition made in this sheet shows without reloading the whole page.
    setQualRows(row.qualifications ?? []);
    try {
      setQualRows(
        await apiClient.listAll<TeacherQualification>('/teacher-qualifications/', `?teacher=${row.id}`),
      );
    } catch {
      // The row's own copy stands. A failed refresh is not worth an error box
      // over data that is already on screen.
    }
  };

  const addQualification = async () => {
    if (!qualTarget || !qualDraft.degree.trim()) return;
    setQualError(null);
    try {
      await apiClient.create<TeacherQualification>('/teacher-qualifications/', {
        teacher: qualTarget.id,
        degree: qualDraft.degree.trim(),
        institution: qualDraft.institution.trim(),
        year: qualDraft.year ? Number(qualDraft.year) : null,
        result: qualDraft.result.trim(),
      });
      setQualDraft(EMPTY_QUALIFICATION);
      setQualRows(
        await apiClient.listAll<TeacherQualification>('/teacher-qualifications/', `?teacher=${qualTarget.id}`),
      );
      await load();
    } catch (err) {
      setQualError(apiErrorText(err, t, t('Could not save this qualification.')));
    }
  };

  const removeQualification = async (id: number) => {
    if (!qualTarget) return;
    try {
      await apiClient.destroy('/teacher-qualifications/', id);
      setQualRows(qualRows.filter((q) => q.id !== id));
      await load();
    } catch (err) {
      setQualError(apiErrorText(err, t, t('Could not delete this qualification.')));
    }
  };

  const columns: Column<Teacher>[] = [
    {
      key: 'name',
      label: t('Teacher'),
      primary: true,
      render: (x) => (
        <span className="block">
          <span className="block">{x.name_bn || x.name}</span>
          <span className="block font-mono text-xs text-gray-500">{x.teacher_id}</span>
        </span>
      ),
    },
    { key: 'designation', label: t('Designation'), render: (x) => x.designation || '—' },
    {
      key: 'streams',
      label: t('Streams'),
      render: (x) => streamNames(x.streams) || t('Every stream'),
    },
    {
      key: 'specialization',
      label: t('Subjects'),
      hideOnNarrow: true,
      render: (x) => x.specialization || '—',
    },
    {
      key: 'joining',
      label: t('Joining date'),
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
      render: (x) => (
        <span className="inline-flex gap-2">
          <button type="button" onClick={() => void openQualifications(x)} className={btnSecondary}>
            {t('Qualifications')}
          </button>
          {mayUpdate && (
            <button type="button" onClick={() => openEdit(x)} className={btnSecondary}>
              {t('Edit')}
            </button>
          )}
        </span>
      ),
    },
  ];

  const filtering = !!(search || statusFilter || streamFilter);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {mayCreate && (
          <button type="button" onClick={openCreate} className={btnPrimary}>
            {t('Add teacher')}
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
            placeholder={t('Search by name, ID or phone')}
            aria-label={t('Search by name, ID or phone')}
            className={filterInputCls}
          />
        }
        active={filtering}
        onClear={() => {
          setSearch('');
          setStatusFilter('');
          setStreamFilter('');
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
          {streams.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name_bn || s.name}
            </option>
          ))}
        </select>
      </FilterBar>

      {loadError && <FormError message={loadError} />}

      <ResponsiveTable
        columns={columns}
        rows={rows}
        rowKey={(x) => x.id}
        empty={loading ? t('Loading…') : t('No teachers yet.')}
        footer={<Pagination total={total} page={page} onChange={setPage} pageSize={PAGE_SIZE} />}
      />

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId === null ? t('Add teacher') : t('Edit teacher')}
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
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
                {t('Teaching')}
              </h3>
              <FieldGrid>
                <Field label={t('Specialization')} error={fieldErrors.specialization}>
                  <input
                    value={draft.specialization}
                    onChange={(e) => setDraft({ ...draft, specialization: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field
                  label={t('Maximum weekly periods')}
                  hint={t('Leave blank for no ceiling.')}
                  error={fieldErrors.max_weekly_periods}
                >
                  <input
                    type="number"
                    inputMode="numeric"
                    value={draft.max_weekly_periods}
                    onChange={(e) => setDraft({ ...draft, max_weekly_periods: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <FieldWide>
                  <Field label={t('Streams')} error={fieldErrors.streams}>
                    {/* Checkboxes rather than a multi-select: a native multiple
                        select needs ctrl-click, which does not exist on a phone. */}
                    <div className="flex flex-wrap gap-2">
                      {streams.map((s) => {
                        const on = draft.streams.includes(s.id);
                        return (
                          <label
                            key={s.id}
                            className={`tap cursor-pointer rounded-lg border px-3 text-sm ${
                              on ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-gray-200 text-gray-700'
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="sr-only"
                              checked={on}
                              onChange={() =>
                                setDraft({
                                  ...draft,
                                  streams: on
                                    ? draft.streams.filter((id) => id !== s.id)
                                    : [...draft.streams, s.id],
                                })
                              }
                            />
                            {s.name_bn || s.name}
                          </label>
                        );
                      })}
                    </div>
                  </Field>
                </FieldWide>
                <FieldWide>
                  <label className="flex min-h-[44px] items-center gap-3">
                    <input
                      type="checkbox"
                      checked={draft.is_class_teacher}
                      onChange={(e) => setDraft({ ...draft, is_class_teacher: e.target.checked })}
                      className="h-5 w-5 rounded border-gray-300 text-blue-600"
                    />
                    <span className="text-sm text-gray-700">{t('May be a class teacher')}</span>
                  </label>
                </FieldWide>
              </FieldGrid>
            </section>
          </div>
        )}
      </BaseModal>

      <BaseModal
        isOpen={qualTarget !== null}
        onClose={() => setQualTarget(null)}
        title={qualTarget ? `${t('Qualifications')} · ${qualTarget.name_bn || qualTarget.name}` : ''}
        maxWidth="2xl"
      >
        <div className="space-y-4">
          <FormError message={qualError} />

          <ul className="divide-y divide-gray-100">
            {qualRows.map((q) => (
              <li key={q.id} className="flex items-start gap-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-gray-900">{q.degree}</span>
                  <span className="block text-xs text-gray-500">
                    {[q.institution, q.year, q.result].filter(Boolean).join(' · ')}
                  </span>
                </span>
                {mayUpdate && (
                  <button
                    type="button"
                    onClick={() => void removeQualification(q.id)}
                    className="tap shrink-0 rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50"
                  >
                    {t('Delete')}
                  </button>
                )}
              </li>
            ))}
            {qualRows.length === 0 && (
              <li className="py-4 text-center text-sm text-gray-500">{t('No qualifications recorded.')}</li>
            )}
          </ul>

          {mayUpdate && (
            <div className="space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
              <FieldGrid>
                <Field label={t('Degree')} required>
                  <input
                    value={qualDraft.degree}
                    onChange={(e) => setQualDraft({ ...qualDraft, degree: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Institution')}>
                  <input
                    value={qualDraft.institution}
                    onChange={(e) => setQualDraft({ ...qualDraft, institution: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Year')}>
                  <input
                    type="number"
                    inputMode="numeric"
                    value={qualDraft.year}
                    onChange={(e) => setQualDraft({ ...qualDraft, year: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Result')}>
                  <input
                    value={qualDraft.result}
                    onChange={(e) => setQualDraft({ ...qualDraft, result: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              </FieldGrid>
              <button
                type="button"
                onClick={() => void addQualification()}
                disabled={!qualDraft.degree.trim()}
                className={`${btnPrimary} w-full sm:w-auto`}
              >
                {t('Add qualification')}
              </button>
            </div>
          )}
        </div>
      </BaseModal>
    </div>
  );
}
