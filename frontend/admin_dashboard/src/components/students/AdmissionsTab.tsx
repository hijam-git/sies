import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  AcademicClass,
  Admission,
  AdmissionStatus,
  AdmitResult,
  FormTemplate,
  Gender,
  Section,
  Session,
  Stream,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import { formatDhakaDate, todayInDhaka } from '../../lib/timezone';
import BaseModal from '../common/BaseModal';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls, btnRowAction } from '../common/styles';
import FormPreviewModal from '../forms/FormPreviewModal';
import type { PreviewRequest } from '../forms/FormPreviewModal';

/**
 * Applications, and the one click that turns one into a student.
 *
 * **Admit is a single transaction with several results.** It creates the
 * Student, the Enrolment, the guardian link and three allocated numbers — the
 * student ID, the admission number and the roll — and the success panel shows
 * all three back, because those are what the office writes on the paper file and
 * there is nowhere else to look them up at that moment.
 *
 * There is no delete: an application that came to nothing is `cancelled`, and
 * the row is the paper trail behind an admission that did happen.
 */

const STATUSES: { value: AdmissionStatus; label: string }[] = [
  { value: 'pending', label: 'Pending' },
  { value: 'interview', label: 'Interview' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'admitted', label: 'Admitted' },
  { value: 'cancelled', label: 'Cancelled' },
];

const GENDERS: { value: Gender; label: string }[] = [
  { value: 'male', label: 'Boy' },
  { value: 'female', label: 'Girl' },
  { value: 'other', label: 'Other' },
];

interface ApplicationDraft {
  session: string;
  stream: string;
  academic_class: string;
  applicant_name: string;
  applicant_name_bn: string;
  dob: string;
  gender: Gender | '';
  guardian_name: string;
  guardian_phone: string;
  village: string;
  post_office: string;
  upazila: string;
  district: string;
  previous_institution: string;
  previous_class: string;
  previous_result: string;
  status: AdmissionStatus;
  remarks: string;
}

function emptyDraft(session: string): ApplicationDraft {
  return {
    session,
    stream: '',
    academic_class: '',
    applicant_name: '',
    applicant_name_bn: '',
    dob: '',
    gender: '',
    guardian_name: '',
    guardian_phone: '',
    village: '',
    post_office: '',
    upazila: '',
    district: '',
    previous_institution: '',
    previous_class: '',
    previous_result: '',
    status: 'pending',
    remarks: '',
  };
}

interface AdmitDraft {
  application: Admission;
  academic_class: string;
  section: string;
  roll: string;
  admitted_on: string;
  is_hostel: boolean;
  is_transport: boolean;
}

export default function AdmissionsTab({
  sessions,
  streams,
  classes,
  sections,
}: {
  sessions: Session[];
  streams: Stream[];
  classes: AcademicClass[];
  sections: Section[];
}) {
  const { t } = useT();
  const { can } = usePermissions();

  const [rows, setRows] = useState<Admission[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  // See `sessionFilter` below: null is "hasn't chosen", '' is "chose all".
  const [sessionChoice, setSessionChoice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<ApplicationDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [admitDraft, setAdmitDraft] = useState<AdmitDraft | null>(null);
  const [admitted, setAdmitted] = useState<AdmitResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('admissions', 'create');
  const mayUpdate = can('admissions', 'update');
  // Printing a form is a `documents` action, not an `admissions` one: the form
  // is a document about the applicant, and an admission officer who may capture
  // an application does not automatically get to issue paper (`docs/02` §2.1).
  const mayPrint = can('documents', 'view');

  // ── Printing (`docs/07` §9) ──────────────────────────────────────────────
  const [preview, setPreview] = useState<PreviewRequest | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [templates, setTemplates] = useState<FormTemplate[]>([]);
  const [templateId, setTemplateId] = useState('');

  useEffect(() => {
    if (!mayPrint) return;
    // The template list is gated on `settings.view`, which a counter clerk does
    // not hold. An empty list is not a failure: printing without naming one
    // uses the institution's default template server-side, which is what the
    // clerk wants every time anyway.
    void apiClient
      .listAll<FormTemplate>('/form-templates/', '?form_type=admission&is_active=true')
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, [mayPrint]);

  const chosenTemplate = templateId ? Number(templateId) : null;

  /** One applicant's filled form. */
  const printOne = (row: Admission) =>
    setPreview({
      key: `filled-${row.id}-${Date.now()}`,
      title: `${t('Admission form')} · ${row.applicant_name_bn || row.applicant_name}`,
      note: t('This copy is recorded and given a form number. Reprint it later from the student’s Documents.'),
      load: async () => [
        await apiClient.admissionFormHtml(row.id, { template: chosenTemplate, mode: 'filled' }),
      ],
    });

  /** Several filled forms, one trip to the printer (`docs/07` §9). */
  const printSelected = () => {
    const chosen = rows.filter((r) => selected.includes(r.id));
    if (chosen.length === 0) return;
    setPreview({
      key: `batch-${chosen.map((r) => r.id).join('-')}-${Date.now()}`,
      title: `${t('Admission forms')} · ${chosen.length}`,
      note: t('Each of these is recorded and given its own form number.'),
      load: () =>
        // Sequential rather than Promise.all: each one takes a row lock to
        // issue its form number, and firing twenty at once at a counter PC
        // only queues them somewhere less visible.
        chosen.reduce<Promise<string[]>>(
          async (soFar, row) => [
            ...(await soFar),
            await apiClient.admissionFormHtml(row.id, {
              template: chosenTemplate,
              mode: 'filled',
            }),
          ],
          Promise.resolve([]),
        ),
    });
  };

  /**
   * The blank stack (`docs/07` §7) — printed in bulk at admission season and
   * filled in by hand.
   *
   * From the template's own preview endpoint when the user may read templates,
   * because a blank needs no applicant to exist. Anyone else falls back to any
   * application with `mode=blank`, which renders the SAME template with an
   * empty context, records nothing and issues no form number.
   */
  const printBlank = () => {
    const template = templates.find((x) => String(x.id) === templateId) ?? templates[0];
    const fallback = rows[0];
    if (!template && !fallback) return;
    setPreview({
      key: `blank-${template?.id ?? 'any'}-${Date.now()}`,
      title: t('Blank admission form'),
      note: t('A blank form to print in a stack and fill in by hand. Nothing is recorded and no form number is issued.'),
      load: async () => [
        template
          ? await apiClient.templatePreviewHtml(template.id, 'blank')
          : await apiClient.admissionFormHtml(fallback.id, { mode: 'blank' }),
      ],
    });
  };

  const toggle = (id: number) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id],
    );

  const pageIds = rows.map((r) => r.id);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.includes(id));

  const defaultSession = useMemo(
    () => String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? ''),
    [sessions],
  );

  // Applications are made for a session, and it is always the current one.
  // Three years of old applications is not what an admission clerk opens this
  // screen to read.
  const sessionFilter = sessionChoice ?? defaultSession;

  /* The filter can change while the request is in the air, and the slower of
   * two answers wins by landing last — under the new heading. */
  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    setLoading(true);
    setLoadError(null);
    try {
      const query = new URLSearchParams({ page: String(page), ordering: '-created_at' });
      if (search.trim()) query.set('search', search.trim());
      if (statusFilter) query.set('status', statusFilter);
      if (sessionFilter) query.set('session', sessionFilter);
      const data = await apiClient.list<Admission>('/admissions/', `?${query}`);
      if (!req.isCurrent(mine)) return;
      setRows(data.results);
      setTotal(data.count);
      // Ticks belong to the page they were made on. Kept across a page change,
      // the toolbar counted seven and "Print selected forms" printed the two
      // that happened to still be on screen — a count that lies about what the
      // button is going to do, on a button that issues paper.
      setSelected((prev) => prev.filter((id) => data.results.some((row) => row.id === id)));
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setLoadError(apiErrorText(err, t, t('Could not load the applications.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [page, search, statusFilter, sessionFilter, req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setDraft(emptyDraft(defaultSession));
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (row: Admission) => {
    setEditingId(row.id);
    setDraft({
      session: String(row.session),
      stream: row.stream === null ? '' : String(row.stream),
      academic_class: row.academic_class === null ? '' : String(row.academic_class),
      applicant_name: row.applicant_name,
      applicant_name_bn: row.applicant_name_bn,
      dob: row.dob ?? '',
      gender: row.gender,
      guardian_name: row.guardian_name,
      guardian_phone: row.guardian_phone,
      village: row.village,
      post_office: row.post_office,
      upazila: row.upazila,
      district: row.district,
      previous_institution: row.previous_institution,
      previous_class: row.previous_class,
      previous_result: row.previous_result,
      status: row.status,
      remarks: row.remarks,
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
      session: Number(draft.session),
      stream: draft.stream ? Number(draft.stream) : null,
      academic_class: draft.academic_class ? Number(draft.academic_class) : null,
      applicant_name: draft.applicant_name.trim(),
      applicant_name_bn: draft.applicant_name_bn.trim(),
      dob: draft.dob || null,
      gender: draft.gender,
      guardian_name: draft.guardian_name.trim(),
      guardian_phone: draft.guardian_phone.trim(),
      village: draft.village.trim(),
      post_office: draft.post_office.trim(),
      upazila: draft.upazila.trim(),
      district: draft.district.trim(),
      previous_institution: draft.previous_institution.trim(),
      previous_class: draft.previous_class.trim(),
      previous_result: draft.previous_result.trim(),
      status: draft.status,
      remarks: draft.remarks.trim(),
    };
    try {
      if (editingId !== null) await apiClient.patch<Admission>('/admissions/', editingId, body);
      else await apiClient.create<Admission>('/admissions/', body);
      setDraft(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this application.')));
    } finally {
      setSaving(false);
    }
  };

  const openAdmit = (row: Admission) => {
    setAdmitted(null);
    setFormError(null);
    setFieldErrors({});
    setAdmitDraft({
      application: row,
      academic_class: row.academic_class === null ? '' : String(row.academic_class),
      section: '',
      roll: '',
      admitted_on: todayInDhaka(),
      is_hostel: false,
      is_transport: false,
    });
  };

  const admit = async () => {
    if (!admitDraft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    try {
      const result = await apiClient.admit(admitDraft.application.id, {
        academic_class: admitDraft.academic_class ? Number(admitDraft.academic_class) : null,
        section: admitDraft.section ? Number(admitDraft.section) : null,
        // Left blank means "allocate the next roll", which is the normal case.
        roll: admitDraft.roll ? Number(admitDraft.roll) : null,
        admitted_on: admitDraft.admitted_on || null,
        is_hostel: admitDraft.is_hostel,
        is_transport: admitDraft.is_transport,
      });
      setAdmitted(result);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not admit this applicant.')));
    } finally {
      setSaving(false);
    }
  };

  const admitSections = useMemo(
    () =>
      admitDraft?.academic_class
        ? sections.filter((s) => String(s.academic_class) === admitDraft.academic_class)
        : [],
    [sections, admitDraft],
  );

  const columns: Column<Admission>[] = [
    ...(mayPrint
      ? ([
          {
            key: 'select',
            label: t('Select'),
            // `action` so the card layout puts it in the footer row with the
            // buttons rather than as a labelled field, where a bare checkbox
            // reads as data the application contains.
            action: true,
            cellClass: 'px-3 py-2 w-10',
            headClass: 'px-3 py-2 w-10',
            render: (a) => (
              <label className="inline-flex min-h-[44px] min-w-[44px] items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.includes(a.id)}
                  onChange={() => toggle(a.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  aria-label={`${t('Select')} ${a.application_no}`}
                />
                <span className="text-xs text-gray-500 md:hidden">{t('Select')}</span>
              </label>
            ),
          },
        ] as Column<Admission>[])
      : []),
    {
      key: 'applicant',
      label: t('Applicant'),
      primary: true,
      render: (a) => (
        <span className="block">
          <span className="block">{a.applicant_name_bn || a.applicant_name}</span>
          <span className="block font-mono text-xs text-gray-500">{a.application_no}</span>
        </span>
      ),
    },
    { key: 'session', label: t('Session'), render: (a) => a.session_name },
    { key: 'stream', label: t('Stream'), hideOnNarrow: true, render: (a) => a.stream_name ?? '—' },
    {
      key: 'guardian',
      label: t('Guardian'),
      render: (a) => (
        <span className="block">
          <span className="block">{a.guardian_name}</span>
          <a href={`tel:${a.guardian_phone}`} className="block font-mono text-xs text-blue-700">
            {a.guardian_phone}
          </a>
        </span>
      ),
    },
    {
      key: 'status',
      label: t('Status'),
      render: (a) => (
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            a.status === 'admitted'
              ? 'bg-emerald-100 text-emerald-800'
              : a.status === 'rejected' || a.status === 'cancelled'
                ? 'bg-gray-100 text-gray-600'
                : 'bg-amber-100 text-amber-800'
          }`}
        >
          {a.status_display}
        </span>
      ),
    },
    {
      key: 'student',
      label: t('Student'),
      hideOnNarrow: true,
      render: (a) => a.student_code ?? '—',
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (a) => (
        <span className="inline-flex flex-wrap justify-end gap-2">
          {mayPrint && (
            <button type="button" onClick={() => printOne(a)} className={btnRowAction}>
              {t('Print form')}
            </button>
          )}
          {mayUpdate && a.status !== 'admitted' && (
            <button type="button" onClick={() => openEdit(a)} className={btnRowAction}>
              {t('Edit')}
            </button>
          )}
          {mayUpdate && a.status !== 'admitted' && a.status !== 'cancelled' && (
            <button type="button" onClick={() => openAdmit(a)} className={btnPrimary}>
              {t('Admit')}
            </button>
          )}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-3">
      {/* Which template, when the institution has more than one. Hidden for the
          single-template case, which is nearly every institution: a select with
          one option is a question with no answer. */}
      {mayPrint && templates.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
          <label htmlFor="admission-form-template">{t('Form template')}</label>
          <select
            id="admission-form-template"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            className={filterSelectCls}
          >
            <option value="">{t('The default form')}</option>
            {templates.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name_bn || x.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* ── Multi-select print (`docs/07` §9) ───────────────────────────── */}
      {mayPrint && rows.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-100 bg-white p-3 shadow-sm">
          <label className="inline-flex min-h-[44px] items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={allOnPageSelected}
              onChange={() =>
                setSelected((current) =>
                  allOnPageSelected
                    ? current.filter((id) => !pageIds.includes(id))
                    : [...new Set([...current, ...pageIds])],
                )
              }
              className="h-5 w-5 rounded border-gray-300 text-blue-600"
            />
            {t('Select all on this page')}
          </label>
          <span className="text-sm text-gray-500">
            {`${selected.length} ${t('selected')}`}
          </span>
          <div className="ml-auto flex flex-wrap gap-2">
            {selected.length > 0 && (
              <button type="button" onClick={() => setSelected([])} className={btnSecondary}>
                {t('Clear')}
              </button>
            )}
            <button
              type="button"
              onClick={printSelected}
              disabled={selected.length === 0}
              className={btnPrimary}
            >
              {t('Print selected forms')}
            </button>
          </div>
        </div>
      )}

      <FilterBar
        actions={
          <>
            {mayPrint && (templates.length > 0 || rows.length > 0) && (
              <button type="button" onClick={printBlank} className={btnSecondary}>
                {t('Print blank form')}
              </button>
            )}
            {mayCreate && (
              <button type="button" onClick={openCreate} className={btnPrimary}>
                {t('New application')}
              </button>
            )}
          </>
        }
        search={
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder={t('Search by applicant, application no. or guardian')}
            aria-label={t('Search by applicant, application no. or guardian')}
            className={filterInputCls}
          />
        }
        active={!!(search || statusFilter || sessionFilter)}
        onClear={() => {
          setSearch('');
          setStatusFilter('');
          // `null`, not `''`: null is "no choice, use the current session" and
          // empty string is "every session". Clearing to the latter put three
          // years of applications on a screen whose own comment says that is
          // not what an admission clerk opens it to read (§7b).
          setSessionChoice(null);
          setPage(1);
        }}
      >
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          aria-label={t('Status')}
          className={filterSelectCls}
        >
          <option value="">{t('Every status')}</option>
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {t(s.label)}
            </option>
          ))}
        </select>
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
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </FilterBar>

      {loadError && <FormError message={loadError} />}

      <ResponsiveTable
        columns={columns}
        rows={rows}
        rowKey={(a) => a.id}
        empty={loading ? t('Loading…') : t('No applications yet.')}
        footer={<Pagination total={total} page={page} onChange={setPage} pageSize={PAGE_SIZE} />}
      />

      {/* ── The application form ─────────────────────────────────────────── */}
      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={editingId === null ? t('New application') : t('Edit application')}
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
            <FieldGrid>
              <Field label={t('Session')} error={fieldErrors.session} required>
                <select
                  value={draft.session}
                  onChange={(e) => setDraft({ ...draft, session: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Choose a session')}</option>
                  {sessions.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Stream')} error={fieldErrors.stream}>
                <select
                  value={draft.stream}
                  onChange={(e) => setDraft({ ...draft, stream: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Not stated')}</option>
                  {streams.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name_bn || s.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Applied for class')} error={fieldErrors.academic_class}>
                <select
                  value={draft.academic_class}
                  onChange={(e) => setDraft({ ...draft, academic_class: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Not stated')}</option>
                  {classes
                    .filter((c) => !draft.session || String(c.session) === draft.session)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name_bn || c.name}
                      </option>
                    ))}
                </select>
              </Field>
              <Field label={t('Status')} error={fieldErrors.status}>
                <select
                  value={draft.status}
                  onChange={(e) => setDraft({ ...draft, status: e.target.value as AdmissionStatus })}
                  className={selectCls}
                >
                  {STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {t(s.label)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Name (English)')} error={fieldErrors.applicant_name} required>
                <input
                  value={draft.applicant_name}
                  onChange={(e) => setDraft({ ...draft, applicant_name: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Name (Bangla)')} error={fieldErrors.applicant_name_bn} required>
                <input
                  value={draft.applicant_name_bn}
                  onChange={(e) => setDraft({ ...draft, applicant_name_bn: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Date of birth')} error={fieldErrors.dob}>
                <input
                  type="date"
                  value={draft.dob}
                  onChange={(e) => setDraft({ ...draft, dob: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Gender')} error={fieldErrors.gender}>
                <select
                  value={draft.gender}
                  onChange={(e) => setDraft({ ...draft, gender: e.target.value as Gender | '' })}
                  className={selectCls}
                >
                  <option value="">{t('Not stated')}</option>
                  {GENDERS.map((g) => (
                    <option key={g.value} value={g.value}>
                      {t(g.label)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Guardian name')} error={fieldErrors.guardian_name} required>
                <input
                  value={draft.guardian_name}
                  onChange={(e) => setDraft({ ...draft, guardian_name: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field
                label={t('Guardian mobile')}
                hint={t('The number the institution calls, and where fee reminders go.')}
                error={fieldErrors.guardian_phone}
                required
              >
                <input
                  type="tel"
                  inputMode="numeric"
                  value={draft.guardian_phone}
                  onChange={(e) => setDraft({ ...draft, guardian_phone: e.target.value })}
                  className={inputCls}
                />
              </Field>
            </FieldGrid>

            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">{t('Address')}</h3>
              <FieldGrid>
                <Field label={t('Village / area')} error={fieldErrors.village}>
                  <input
                    value={draft.village}
                    onChange={(e) => setDraft({ ...draft, village: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Post office')} error={fieldErrors.post_office}>
                  <input
                    value={draft.post_office}
                    onChange={(e) => setDraft({ ...draft, post_office: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Upazila / thana')} error={fieldErrors.upazila}>
                  <input
                    value={draft.upazila}
                    onChange={(e) => setDraft({ ...draft, upazila: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('District')} error={fieldErrors.district}>
                  <input
                    value={draft.district}
                    onChange={(e) => setDraft({ ...draft, district: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              </FieldGrid>
            </section>

            <section>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
                {t('Previous schooling')}
              </h3>
              <FieldGrid>
                <Field label={t('Previous institution')} error={fieldErrors.previous_institution}>
                  <input
                    value={draft.previous_institution}
                    onChange={(e) => setDraft({ ...draft, previous_institution: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Previous class')} error={fieldErrors.previous_class}>
                  <input
                    value={draft.previous_class}
                    onChange={(e) => setDraft({ ...draft, previous_class: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label={t('Previous result')} error={fieldErrors.previous_result}>
                  <input
                    value={draft.previous_result}
                    onChange={(e) => setDraft({ ...draft, previous_result: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <FieldWide>
                  <Field label={t('Remarks')} error={fieldErrors.remarks}>
                    <input
                      value={draft.remarks}
                      onChange={(e) => setDraft({ ...draft, remarks: e.target.value })}
                      className={inputCls}
                    />
                  </Field>
                </FieldWide>
              </FieldGrid>
            </section>
          </div>
        )}
      </BaseModal>

      {/* ── Admit ────────────────────────────────────────────────────────── */}
      <BaseModal
        isOpen={admitDraft !== null}
        onClose={() => {
          setAdmitDraft(null);
          setAdmitted(null);
        }}
        title={t('Admit')}
        maxWidth="lg"
        footer={
          admitted ? (
            <button
              type="button"
              onClick={() => {
                setAdmitDraft(null);
                setAdmitted(null);
              }}
              className={`${btnPrimary} w-full`}
            >
              {t('Done')}
            </button>
          ) : (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setAdmitDraft(null)}
                // Not while the admission is in flight: it commits server-side
                // either way, and this panel is the only place the new student
                // id, admission number and roll are ever shown.
                disabled={saving}
                className={`${btnSecondary} flex-1`}
              >
                {t('Cancel')}
              </button>
              <button
                type="button"
                onClick={() => void admit()}
                disabled={saving}
                className={`${btnPrimary} flex-1`}
              >
                {saving ? t('Admitting…') : t('Admit')}
              </button>
            </div>
          )
        }
      >
        {admitDraft && (
          <div className="space-y-3">
            <FormError message={formError} />

            {admitted ? (
              // What the transaction produced. Three numbers the office needs at
              // this exact moment, and nowhere else to read them from.
              <div className="space-y-3">
                <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                  {`${admitted.student.name_bn || admitted.student.name} ${t('is admitted.')}`}
                </p>
                <dl className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                  <div className="flex items-center justify-between gap-3 px-3 py-2">
                    <dt className="text-xs uppercase tracking-wide text-gray-400">{t('Student ID')}</dt>
                    <dd className="font-mono text-sm font-semibold text-gray-900">
                      {admitted.student.student_id}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 px-3 py-2">
                    <dt className="text-xs uppercase tracking-wide text-gray-400">{t('Admission no.')}</dt>
                    <dd className="font-mono text-sm font-semibold text-gray-900">
                      {admitted.admission_number ?? '—'}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between gap-3 px-3 py-2">
                    <dt className="text-xs uppercase tracking-wide text-gray-400">{t('Roll')}</dt>
                    <dd className="font-mono text-sm font-semibold text-gray-900">{admitted.roll ?? '—'}</dd>
                  </div>
                </dl>
                <p className="text-xs text-gray-500">
                  {t('A login is not part of this. Open the student record to give them one.')}
                </p>
              </div>
            ) : (
              <>
                <p className="text-sm text-gray-600">
                  {admitDraft.application.applicant_name_bn || admitDraft.application.applicant_name}
                  {' · '}
                  {admitDraft.application.application_no}
                </p>

                <Field label={t('Class')} error={fieldErrors.academic_class} required>
                  <select
                    value={admitDraft.academic_class}
                    onChange={(e) =>
                      setAdmitDraft({ ...admitDraft, academic_class: e.target.value, section: '' })
                    }
                    className={selectCls}
                  >
                    <option value="">{t('Choose a class')}</option>
                    {classes
                      .filter((c) => String(c.session) === String(admitDraft.application.session))
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name_bn || c.name}
                        </option>
                      ))}
                  </select>
                </Field>

                <Field label={t('Section')} error={fieldErrors.section}>
                  <select
                    value={admitDraft.section}
                    onChange={(e) => setAdmitDraft({ ...admitDraft, section: e.target.value })}
                    className={selectCls}
                  >
                    <option value="">{t('Not stated')}</option>
                    {admitSections.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name_bn || s.name}
                      </option>
                    ))}
                  </select>
                </Field>

                <FieldGrid>
                  <Field
                    label={t('Roll')}
                    hint={t('Leave blank and the next roll is allocated.')}
                    error={fieldErrors.roll}
                  >
                    <input
                      type="number"
                      inputMode="numeric"
                      value={admitDraft.roll}
                      onChange={(e) => setAdmitDraft({ ...admitDraft, roll: e.target.value })}
                      className={inputCls}
                    />
                  </Field>
                  <Field label={t('Admitted on')} error={fieldErrors.admitted_on}>
                    <input
                      type="date"
                      value={admitDraft.admitted_on}
                      onChange={(e) => setAdmitDraft({ ...admitDraft, admitted_on: e.target.value })}
                      className={inputCls}
                    />
                  </Field>
                </FieldGrid>

                <label className="flex min-h-[44px] items-center gap-3">
                  <input
                    type="checkbox"
                    checked={admitDraft.is_hostel}
                    onChange={(e) => setAdmitDraft({ ...admitDraft, is_hostel: e.target.checked })}
                    className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">{t('Lives in the hostel')}</span>
                </label>
                <label className="flex min-h-[44px] items-center gap-3">
                  <input
                    type="checkbox"
                    checked={admitDraft.is_transport}
                    onChange={(e) => setAdmitDraft({ ...admitDraft, is_transport: e.target.checked })}
                    className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">{t('Uses the transport')}</span>
                </label>

                <p className="text-xs leading-relaxed text-gray-500">
                  {t('One step: the student record, the enrolment, the guardian and the numbers are all created together, or none of them are.')}
                </p>
                {admitDraft.application.created_at && (
                  <p className="text-xs text-gray-400">
                    {t('Applied on')} {formatDhakaDate(admitDraft.application.created_at)}
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </BaseModal>

      <FormPreviewModal request={preview} onClose={() => setPreview(null)} />
    </div>
  );
}
