import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { AcademicClass, Enrolment, Section, Session, Student, Stream } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import Picker from '../common/Picker';
import ResponsiveTable, { cellTapCls } from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { FormError } from '../common/Field';
import StatusDot from '../common/StatusDot';
import { btnPrimary, btnRowAction, btnSecondary } from '../common/styles';
import StudentFormModal from './StudentFormModal';
import StudentDetailModal from './StudentDetailModal';
import RollChangeModal from './RollChangeModal';

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
 *    of a page filtered down to three rows. Read in **roll order** then, since
 *    a class list is read the way the register is called.
 *
 * The roll column is the class roll (শ্রেণি রোল), and it is where a roll is
 * changed: tap it, type the new number, and if somebody in the class already
 * has it the dialog offers to swap the two.
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
  /** Bumped to re-read the register after a roll changes. */
  const [enrolmentsRev, setEnrolmentsRev] = useState(0);
  const [rollTarget, setRollTarget] = useState<{ student: Student; enrolment: Enrolment } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [detailId, setDetailId] = useState<number | null>(null);
  const [formTarget, setFormTarget] = useState<Student | null | undefined>(undefined);

  const mayCreate = can('students', 'create');
  const mayUpdate = can('students', 'update');
  // The server accepts any one of the three: the office keeps the records, the
  // academic side keeps the classes, the admission desk issued the roll.
  const mayChangeRoll =
    can('students', 'update') || can('academics', 'update') || can('admissions', 'update');

  const sessionId =
    sessionChoice || String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? '');

  // The session's whole register, read once. It is what puts a class and a
  // section beside every name, and what the class filter narrows by.
  useEffect(() => {
    if (!sessionId) return;
    void apiClient
      .listAll<Enrolment>('/enrolments/', `?session=${sessionId}&is_active=true`)
      .then(setEnrolments)
      // Not silently empty: this is what puts a class and a section beside
      // every name, and a blank Class column reads like "not enrolled".
      .catch((err) => setLoadError(apiErrorText(err, t, t('Could not load the class list.'))));
  }, [sessionId, enrolmentsRev, t]);

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

  /* Every load here is keyed on a filter the user can change while the request
   * is in the air, and the slower of two answers wins by landing last. The
   * debounce below does not cover it — it only cancels a request that has not
   * started. `req` says whether this answer is still the one being waited for.
   */
  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    setLoading(true);
    setLoadError(null);
    const filters = new URLSearchParams();
    if (search.trim()) filters.set('search', search.trim());
    if (streamFilter) filters.set('stream', streamFilter);
    if (statusFilter) filters.set('status', statusFilter);

    try {
      if (byClassSection) {
        const all = await apiClient.listAll<Student>('/students/', `?${filters}`);
        if (!req.isCurrent(mine)) return;
        const matching = all.filter((s) => byClassSection.has(s.id));
        // Roll order — section first, because rolls restart per section and a
        // whole-class list would otherwise read A-1, B-1, A-2.
        const sectionOrder = (id: number | null) =>
          id === null ? '' : (sections.find((x) => x.id === id)?.name ?? '');
        matching.sort((a, b) => {
          const ea = enrolmentOf.get(a.id);
          const eb = enrolmentOf.get(b.id);
          const bySection = sectionOrder(ea?.section ?? null).localeCompare(
            sectionOrder(eb?.section ?? null),
          );
          if (bySection !== 0) return bySection;
          return (ea?.roll ?? Number.MAX_SAFE_INTEGER) - (eb?.roll ?? Number.MAX_SAFE_INTEGER);
        });
        setTotal(matching.length);
        setRows(matching.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE));
      } else {
        const data = await apiClient.list<Student>('/students/', `?${filters}&page=${page}`);
        if (!req.isCurrent(mine)) return;
        setRows(data.results);
        setTotal(data.count);
      }
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setLoadError(apiErrorText(err, t, t('Could not load the students.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [page, search, streamFilter, statusFilter, byClassSection, enrolmentOf, sections, req, t]);

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
      // Name and ID on ONE line. Stacked, they set the height of every row in
      // the roll for the sake of a code nobody reads twice. There is no
      // initial-in-a-circle either: it is 36px of the same letter the name
      // beside it already starts with. A real photo, when there is one, is
      // h-7 so it fits inside the row rather than defining it.
      render: (s) => (
        <span className="flex min-w-0 items-center gap-2">
          {s.photo && (
            <img src={s.photo} alt="" className="h-7 w-7 shrink-0 rounded-full object-cover" />
          )}
          <span className="truncate">{s.name_bn || s.name}</span>
          <span className="shrink-0 font-mono text-xs text-gray-400">{s.student_id}</span>
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
      label: t('Class roll'),
      render: (s) => {
        const e = enrolmentOf.get(s.id);
        if (!e) return '—';
        if (!mayChangeRoll) return e.roll ?? '—';
        return (
          <button
            type="button"
            onClick={(event) => {
              // The row opens the student; this opens the roll and nothing else.
              event.stopPropagation();
              setNotice(null);
              setRollTarget({ student: s, enrolment: e });
            }}
            className={btnRowAction}
            title={t('Change class roll')}
            aria-label={`${t('Change class roll')} — ${s.name_bn || s.name}`}
          >
            <span className="font-semibold tabular-nums">{e.roll ?? '—'}</span>
            <span aria-hidden="true" className="text-gray-400">✎</span>
          </button>
        );
      },
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
            onClick={(e) => e.stopPropagation()}
            className={`${cellTapCls} font-mono text-blue-700`}
          >
            {primary.guardian_phone}
          </a>
        );
      },
    },
    {
      key: 'status',
      label: t('Status'),
      // `status_display` is both languages joined; STATUSES is the one the
      // reader is actually in.
      render: (s) => (
        <StatusDot
          tone={s.status === 'active' ? 'green' : 'gray'}
          label={t(STATUSES.find((x) => x.value === s.status)?.label ?? '') || s.status_display}
        />
      ),
    },
    {
      key: 'actions',
      label: t('Actions'),
      action: true,
      // Phone only: from md the row itself opens the student, so a button
      // saying so in all twenty-five rows is 25 × 44px of repetition. A card
      // has no hover to reveal that, so it keeps the button.
      cardOnly: true,
      render: (s) => (
        <button type="button" onClick={() => setDetailId(s.id)} className={btnSecondary}>
          {t('Open')}
        </button>
      ),
    },
  ];

  const filtering = !!(search || streamFilter || classFilter || sectionFilter || statusFilter !== 'active');

  return (
    <div className="space-y-3">
      <FilterBar
        actions={
          mayCreate && (
            <button type="button" onClick={() => setFormTarget(null)} className={btnPrimary}>
              {t('Add student')}
            </button>
          )
        }
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
      {notice && (
        <p className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          {notice}
        </p>
      )}

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

      {rollTarget && (
        <RollChangeModal
          enrolment={rollTarget.enrolment}
          studentName={rollTarget.student.name_bn || rollTarget.student.name}
          classLabel={`${rollTarget.enrolment.class_name}${
            rollTarget.enrolment.section !== null
              ? ` · ${sectionName(rollTarget.enrolment.section)}`
              : ''
          }`}
          peers={enrolments.filter(
            (e) =>
              e.academic_class === rollTarget.enrolment.academic_class &&
              e.section === rollTarget.enrolment.section,
          )}
          onClose={() => setRollTarget(null)}
          onSaved={(message) => {
            setNotice(message);
            setEnrolmentsRev((n) => n + 1);
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
