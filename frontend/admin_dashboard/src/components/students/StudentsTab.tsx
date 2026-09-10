import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass, Enrolment, Section, Session, Student, Stream } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import Picker from '../common/Picker';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary } from '../common/styles';
import StudentFormModal from './StudentFormModal';
import StudentDetailModal from './StudentDetailModal';

/**
 * The student roll.
 *
 * **Class and section are not on the student record.** They live on the
 * session's Enrolment rows, so the register for the chosen session is read once
 * and joined here — which is also why filtering by class works the way it does
 * below: the API cannot filter students by a column students do not have.
 *
 * Two fetch strategies, and the difference is deliberate rather than an
 * accident of growth:
 *
 *  - **No class or section filter** — the server paginates, as everywhere else.
 *    Search, stream and status are all real query parameters.
 *  - **A class or section chosen** — the matching students are the ones named
 *    by the session's enrolments, an intersection the API has no way to express.
 *    The (already loaded) enrolments decide the set and the list is paged here,
 *    so the count and the page numbers still describe what is on screen instead
 *    of a page filtered down to three rows.
 */

const STATUSES = [
  { value: 'active', label: 'Active' },
  { value: 'passed_out', label: 'Passed out' },
  { value: 'withdrawn', label: 'Withdrawn' },
  { value: 'transferred', label: 'Transferred' },
];

export default function StudentsTab({
  streams,
  classes,
  sections,
  sessions,
}: {
  streams: Stream[];
  classes: AcademicClass[];
  sections: Section[];
  sessions: Session[];
}) {
  const { t } = useT();
  const { can } = usePermissions();

  // The CHOICE, defaulting to the current session. Derived rather than written
  // from an effect, which would render once with no session and again with it.
  const [sessionChoice, setSessionChoice] = useState('');
  const [rows, setRows] = useState<Student[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [streamFilter, setStreamFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [classFilter, setClassFilter] = useState('');
  const [sectionFilter, setSectionFilter] = useState('');
  const [enrolments, setEnrolments] = useState<Enrolment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [detailId, setDetailId] = useState<number | null>(null);
  const [formTarget, setFormTarget] = useState<Student | null | undefined>(undefined);

  const mayCreate = can('students', 'create');
  const mayUpdate = can('students', 'update');

  const sessionId =
    sessionChoice || String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? '');

  // The session's whole register, read once. It is what puts a class and a
  // section beside every name, and what the class filter narrows by.
  useEffect(() => {
    if (!sessionId) return;
    void apiClient
      .listAll<Enrolment>('/enrolments/', `?session=${sessionId}&is_active=true`)
      .then(setEnrolments)
      .catch(() => setEnrolments([]));
  }, [sessionId]);

  const enrolmentOf = useMemo(() => {
    const byStudent = new Map<number, Enrolment>();
    for (const e of enrolments) byStudent.set(e.student, e);
    return byStudent;
  }, [enrolments]);

  const byClassSection = useMemo(() => {
    if (!classFilter && !sectionFilter) return null;
    const ids = new Set<number>();
    for (const e of enrolments) {
      if (classFilter && String(e.academic_class) !== classFilter) continue;
      if (sectionFilter && String(e.section ?? '') !== sectionFilter) continue;
      ids.add(e.student);
    }
    return ids;
  }, [enrolments, classFilter, sectionFilter]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    const filters = new URLSearchParams();
    if (search.trim()) filters.set('search', search.trim());
    if (streamFilter) filters.set('stream', streamFilter);
    if (statusFilter) filters.set('status', statusFilter);

    try {
      if (byClassSection) {
        const all = await apiClient.listAll<Student>('/students/', `?${filters}`);
        const matching = all.filter((s) => byClassSection.has(s.id));
        setTotal(matching.length);
        setRows(matching.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE));
      } else {
        const data = await apiClient.list<Student>('/students/', `?${filters}&page=${page}`);
        setRows(data.results);
        setTotal(data.count);
      }
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the students.')));
    } finally {
      setLoading(false);
    }
  }, [page, search, streamFilter, statusFilter, byClassSection, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const sectionName = useCallback(
    (id: number | null) => {
      if (id === null) return '';
      const section = sections.find((s) => s.id === id);
      return section ? section.name_bn || section.name : '';
    },
    [sections],
  );

  const sectionsOfClass = useMemo(
    () => (classFilter ? sections.filter((s) => String(s.academic_class) === classFilter) : sections),
    [sections, classFilter],
  );

  const columns: Column<Student>[] = [
    {
      key: 'name',
      label: t('Student'),
      primary: true,
      render: (s) => (
        <span className="flex items-center gap-3">
          {s.photo ? (
            <img src={s.photo} alt="" className="h-9 w-9 shrink-0 rounded-full object-cover" />
          ) : (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gray-100 text-sm text-gray-400">
              {(s.name_bn || s.name).slice(0, 1)}
            </span>
          )}
          <span className="min-w-0">
            <span className="block truncate">{s.name_bn || s.name}</span>
            <span className="block font-mono text-xs text-gray-500">{s.student_id}</span>
          </span>
        </span>
      ),
    },
    { key: 'stream', label: t('Stream'), render: (s) => s.stream_name ?? '—' },
    {
      key: 'class',
      label: t('Class'),
      render: (s) => {
        const e = enrolmentOf.get(s.id);
        if (!e) return <span className="text-gray-400">{t('Not enrolled')}</span>;
        const section = sectionName(e.section);
        return `${e.class_name}${section ? ` · ${section}` : ''}`;
      },
    },
    {
      key: 'roll',
      label: t('Roll'),
      hideOnNarrow: true,
      render: (s) => enrolmentOf.get(s.id)?.roll ?? '—',
    },
    {
      key: 'guardian',
      label: t('Guardian'),
      render: (s) => {
        const primary = s.guardians.find((g) => g.is_primary) ?? s.guardians[0];
        if (!primary) return '—';
        return (
          // A guardian's number on a phone is the link people actually tap —
          // it is how the office rings a parent. It gets a real 44px target
          // rather than a 16px line of text (`CLAUDE.md` §7a rule 4).
          <a
            href={`tel:${primary.guardian_phone}`}
            className="inline-flex min-h-[44px] items-center font-mono text-blue-700"
          >
            {primary.guardian_phone}
          </a>
        );
      },
    },
    {
      key: 'status',
      label: t('Status'),
      render: (s) => (
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            s.status === 'active' ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {s.status_display}
        </span>
      ),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      cellClass: 'px-4 py-3 text-right',
      headClass: 'px-4 py-3 text-right',
      render: (s) => (
        <button type="button" onClick={() => setDetailId(s.id)} className={btnSecondary}>
          {t('Open')}
        </button>
      ),
    },
  ];

  const filtering = !!(search || streamFilter || classFilter || sectionFilter || statusFilter !== 'active');

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-gray-500">
          {t('The roll. A student’s class comes from the session’s register, not from their record.')}
        </p>
        {mayCreate && (
          <button type="button" onClick={() => setFormTarget(null)} className={btnPrimary}>
            {t('Add student')}
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
            placeholder={t('Search by name, student ID or phone')}
            aria-label={t('Search by name, student ID or phone')}
            className={filterInputCls}
          />
        }
        active={filtering}
        onClear={() => {
          setSearch('');
          setStreamFilter('');
          setClassFilter('');
          setSectionFilter('');
          setStatusFilter('active');
          setPage(1);
        }}
      >
        <Picker
          value={sessionId}
          onChange={(v) => {
            setSessionChoice(v);
            setPage(1);
          }}
          options={sessions.map((s) => ({ value: String(s.id), label: s.name }))}
          aria-label={t('Session')}
          className={filterSelectCls}
        />
        <select
          value={classFilter}
          onChange={(e) => {
            setClassFilter(e.target.value);
            setSectionFilter('');
            setPage(1);
          }}
          aria-label={t('Class')}
          className={filterSelectCls}
        >
          <option value="">{t('Every class')}</option>
          {classes
            .filter((c) => !sessionId || String(c.session) === sessionId)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.name_bn || c.name}
              </option>
            ))}
        </select>
        <select
          value={sectionFilter}
          onChange={(e) => {
            setSectionFilter(e.target.value);
            setPage(1);
          }}
          aria-label={t('Section')}
          className={filterSelectCls}
        >
          <option value="">{t('Every section')}</option>
          {sectionsOfClass.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name_bn || s.name}
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
      </FilterBar>

      {loadError && <FormError message={loadError} />}

      <ResponsiveTable
        columns={columns}
        rows={rows}
        rowKey={(s) => s.id}
        onRowClick={(s) => setDetailId(s.id)}
        empty={loading ? t('Loading…') : t('No students match this.')}
        footer={<Pagination total={total} page={page} onChange={setPage} pageSize={PAGE_SIZE} />}
      />

      {detailId !== null && (
        <StudentDetailModal
          studentId={detailId}
          sectionName={sectionName}
          onClose={() => setDetailId(null)}
          onChanged={load}
          onEdit={(student) => {
            if (!mayUpdate) return;
            setDetailId(null);
            setFormTarget(student);
          }}
        />
      )}

      {formTarget !== undefined && (
        <StudentFormModal
          student={formTarget}
          streams={streams}
          onClose={() => setFormTarget(undefined)}
          onSaved={load}
        />
      )}
    </div>
  );
}
