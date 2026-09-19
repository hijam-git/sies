import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '../../lib/api';
import type {
  ExamSchedule,
  ExamStatus,
  Student,
  StudentReport,
  StudentReportExam,
  Tabulation,
  TabulationRow,
} from '../../lib/api';
import { useAuth, usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';
import { preferredClassId, preferredExamId, useOwnTeacherId } from '../../lib/defaults';
import { EXAM_TYPES, classLabel, examLabel } from './shared';
import type { ExamsData } from './shared';

/**
 * Results — built for *finding* a result, which is what this screen is opened
 * for nine times out of ten.
 *
 * Two questions, two views, one search box that answers the second from
 * anywhere:
 *
 * - **Class results** — "how did Class 5 খ do in the half-yearly?" Session,
 *   exam, class and section are chips rather than dropdowns, so every
 *   alternative is visible and one tap away; the sheet opens on the current
 *   session's live exam and the reader's own class. A summary strip answers the
 *   first thing anyone asks (how many passed), and the sheet can be searched,
 *   filtered to failures, sorted by merit and printed.
 * - **Student results** — "what did Rahim get?" Type a name, ID or phone, pick
 *   the student, and every exam they have sat is listed with grade, rank in
 *   class and in section, and the subject lines one tap below. Each exam prints
 *   as a marksheet.
 *
 * **Every choice lives in the URL** (`?view=student&student=12`, `?exam=…&class=
 * …&section=…`). A result is a thing people send each other and come back to;
 * Back from a student returns to the exact sheet they were opened from.
 *
 * Publishing stays here, gated on `exams.publish` and confirmed in a sentence
 * that says what will happen (`docs/02` §2.1). There is no unpublish.
 */

type View = 'class' | 'student';
type Outcome = 'all' | 'passed' | 'failed';
type SortKey = 'roll' | 'rank';
type Update = (changes: Record<string, string | null>) => void;
type Translate = (key: string) => string;

const n = (value: string | number | null | undefined): number =>
  value === null || value === undefined || value === '' ? 0 : Number(value);

/** `78.5`, not `78.50`; `80`, not `80.00`. */
function fmt(value: string | number | null | undefined): string {
  const x = n(value);
  return Number.isInteger(x) ? String(x) : String(Math.round(x * 100) / 100);
}

const chipCls = (active: boolean) =>
  `inline-flex min-h-[32px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md border px-3 text-[13px] font-medium transition-colors ${
    active
      ? 'border-blue-600 bg-blue-600 text-white shadow-sm shadow-blue-600/20'
      : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50'
  }`;

const STATUS_DOT: Record<ExamStatus, string> = {
  draft: 'bg-gray-300',
  scheduled: 'bg-blue-400',
  ongoing: 'bg-blue-500',
  marks_entry: 'bg-amber-400',
  published: 'bg-green-500',
};

export default function ResultsTab({ data }: { data: ExamsData }) {
  const { t } = useT();
  const [params, setParams] = useSearchParams();
  const view: View = params.get('view') === 'student' ? 'student' : 'class';

  const update: Update = (changes) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next);
  };

  const openStudent = (studentId: number, examId?: number) =>
    update({ view: 'student', student: String(studentId), focus: examId ? String(examId) : null });

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center print:hidden">
        <div className="inline-flex h-9 shrink-0 items-center gap-0.5 self-start rounded-lg bg-gray-100 p-0.5">
          {(['class', 'student'] as const).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={view === key}
              onClick={() => update({ view: key === 'class' ? null : 'student' })}
              className={`h-8 whitespace-nowrap rounded-md px-3 text-[13px] font-medium transition-all ${
                view === key
                  ? 'bg-white text-gray-900 shadow-sm ring-1 ring-gray-900/5'
                  : 'text-gray-500 hover:text-gray-800'
              }`}
            >
              {key === 'class' ? t('Class results') : t('Student results')}
            </button>
          ))}
        </div>
        {/* Always here, in both views: the fastest way to any one result is
            the student's name, whatever sheet happens to be open. */}
        <div className="sm:ml-auto sm:w-80">
          <StudentFinder onPick={(student) => openStudent(student.id)} />
        </div>
      </div>

      {view === 'class' ? (
        <ClassResults data={data} params={params} update={update} onOpenStudent={openStudent} />
      ) : (
        <StudentResults studentId={params.get('student') ?? ''} focusExam={params.get('focus') ?? ''} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Finding a student
// ─────────────────────────────────────────────────────────────────────────────

function StudentFinder({ onPick }: { onPick: (student: Student) => void }) {
  const { t, lang } = useT();
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<{ term: string; rows: Student[]; error: string | null }>({
    term: '',
    rows: [],
    error: null,
  });
  const [open, setOpen] = useState(false);
  const term = query.trim();

  useEffect(() => {
    if (term.length < 2) return;
    const timer = setTimeout(() => {
      apiClient
        .list<Student>('/students/', `?search=${encodeURIComponent(term)}&page=1`)
        .then((page) => setFound({ term, rows: page.results.slice(0, 8), error: null }))
        .catch((err) =>
          setFound({ term, rows: [], error: apiErrorText(err, t, t('Could not search students.')) }),
        );
    }, 250);
    return () => clearTimeout(timer);
  }, [term, t]);

  const ready = term.length >= 2 && found.term === term;
  const rows = ready ? found.rows : [];

  const pick = (student: Student) => {
    onPick(student);
    setQuery('');
    setOpen(false);
  };

  return (
    <div className="relative">
      <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
      <input
        type="search"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        // Deferred so a click on a result lands before the list disappears.
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && rows[0]) {
            e.preventDefault();
            pick(rows[0]);
          }
          if (e.key === 'Escape') setOpen(false);
        }}
        placeholder={t('Find a student by name, ID or phone')}
        aria-label={t('Find a student by name, ID or phone')}
        className={`${inputCls} pl-9 sm:pl-9`}
      />
      {open && term.length >= 2 && (
        <div className="absolute left-0 right-0 z-30 mt-1 max-h-80 overflow-y-auto rounded-xl border border-gray-200 bg-white p-1 shadow-xl shadow-gray-900/10">
          {!ready ? (
            <p className="px-3 py-2 text-sm text-gray-400">{t('Loading…')}</p>
          ) : found.error ? (
            <p className="px-3 py-2 text-sm text-red-700">{found.error}</p>
          ) : rows.length === 0 ? (
            <p className="px-3 py-2 text-sm text-gray-500">{t('No student matches this.')}</p>
          ) : (
            rows.map((student) => (
              <button
                key={student.id}
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(student);
                }}
                className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left hover:bg-blue-50"
              >
                <Avatar name={lang === 'bn' ? student.name_bn || student.name : student.name} photo={student.photo} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-gray-900">
                    {lang === 'bn' ? student.name_bn || student.name : student.name}
                  </span>
                  <span className="block truncate text-xs text-gray-500">
                    <span className="font-mono">{student.student_id}</span>
                    {student.stream_name ? ` · ${student.stream_name}` : ''}
                  </span>
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Class results
// ─────────────────────────────────────────────────────────────────────────────

function ClassResults({
  data,
  params,
  update,
  onOpenStudent,
}: {
  data: ExamsData;
  params: URLSearchParams;
  update: Update;
  onOpenStudent: (studentId: number, examId?: number) => void;
}) {
  const { t, lang } = useT();
  const { can } = usePermissions();
  const ownTeacherId = useOwnTeacherId(data.teachers);
  const mayPublish = can('exams', 'publish');

  const [schedules, setSchedules] = useState<ExamSchedule[]>([]);
  const [sheet, setSheet] = useState<Tabulation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [outcome, setOutcome] = useState<Outcome>('all');
  const [sort, setSort] = useState<SortKey>('roll');
  const [confirming, setConfirming] = useState(false);
  const [publishing, setPublishing] = useState(false);

  // Session → exam → class → section. Each is the URL's choice when it is still
  // valid, and otherwise the obvious default (`CLAUDE.md` §7b): the current
  // session, its live exam, the reader's own class, the whole class.
  const sessionParam = params.get('session') ?? '';
  const sessionId = data.sessions.some((s) => String(s.id) === sessionParam)
    ? sessionParam
    : String((data.sessions.find((s) => s.is_current) ?? data.sessions[0])?.id ?? '');

  const sessionExams = useMemo(
    () =>
      data.exams
        .filter((e) => !sessionId || String(e.session) === sessionId)
        .sort((a, b) => b.starts_on.localeCompare(a.starts_on)),
    [data.exams, sessionId],
  );

  const examParam = params.get('exam') ?? '';
  const examId = sessionExams.some((e) => String(e.id) === examParam)
    ? examParam
    : preferredExamId(sessionExams);
  const exam = sessionExams.find((e) => String(e.id) === examId);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (!examId) {
        setSchedules([]);
        return;
      }
      void apiClient
        .listAll<ExamSchedule>('/exam-schedules/', `?exam=${examId}`)
        .then(setSchedules)
        .catch(() => setSchedules([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [examId]);

  const paperClasses = useMemo(() => {
    const ids = new Set(
      schedules.filter((s) => String(s.exam) === examId).map((s) => String(s.academic_class)),
    );
    return data.classes.filter((c) => ids.has(String(c.id)));
  }, [schedules, data.classes, examId]);

  const classParam = params.get('class') ?? '';
  const classId = paperClasses.some((c) => String(c.id) === classParam)
    ? classParam
    : preferredClassId(paperClasses, ownTeacherId);
  const chosenClass = paperClasses.find((c) => String(c.id) === classId);

  const subjectColumns = useMemo(
    () =>
      schedules
        .filter((s) => String(s.exam) === examId && String(s.academic_class) === classId)
        .map((s) => ({
          id: s.subject,
          name: s.subject_name,
          full: n(s.full_marks),
          pass: n(s.pass_marks),
        })),
    [schedules, examId, classId],
  );

  const load = useCallback(async () => {
    if (!examId || !classId) {
      setSheet(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setSheet(await apiClient.getTabulation(Number(examId), Number(classId)));
    } catch (err) {
      setSheet(null);
      setError(apiErrorText(err, t, t('Could not load the tabulation sheet.')));
    } finally {
      setLoading(false);
    }
  }, [examId, classId, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  // The sheet for what is chosen NOW — a response for the previous exam or
  // class is not shown under the new one's heading while the next loads.
  const current =
    sheet && String(sheet.exam) === examId && String(sheet.academic_class) === classId ? sheet : null;

  const sections = useMemo(() => current?.sections ?? [], [current]);
  const sectionParam = params.get('section') ?? '';
  const sectionId = sections.some((s) => String(s.id) === sectionParam) ? sectionParam : '';
  const chosenSection = sections.find((s) => String(s.id) === sectionId);

  const scoped = useMemo(
    () => (current?.rows ?? []).filter((row) => !sectionId || String(row.section) === sectionId),
    [current, sectionId],
  );

  const stats = useMemo(() => {
    const withMarks = scoped.filter((row) => Object.keys(row.marks).length > 0);
    const passed = withMarks.filter((row) => row.is_passed).length;
    const percentages = withMarks.map((row) => n(row.percentage));
    return {
      examinees: scoped.length,
      notEntered: scoped.length - withMarks.length,
      passed,
      failed: withMarks.length - passed,
      passRate: withMarks.length ? Math.round((passed / withMarks.length) * 100) : 0,
      highest: percentages.length ? Math.max(...percentages) : 0,
      average: percentages.length ? percentages.reduce((a, b) => a + b, 0) / percentages.length : 0,
    };
  }, [scoped]);

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rankOf = (row: TabulationRow) => (sectionId ? row.rank_in_section : row.rank_in_class);
    const rows = scoped.filter((row) => {
      const hasMarks = Object.keys(row.marks).length > 0;
      if (outcome === 'passed' && !row.is_passed) return false;
      if (outcome === 'failed' && (row.is_passed || !hasMarks)) return false;
      if (!q) return true;
      return [row.student_name, row.student_name_bn, row.student_code, row.roll === null ? '' : String(row.roll)]
        .some((value) => (value ?? '').toLowerCase().includes(q));
    });
    return [...rows].sort((a, b) => {
      if (sort === 'rank') {
        const ra = rankOf(a);
        const rb = rankOf(b);
        if (ra !== null && rb !== null) return ra - rb;
        if (ra !== null) return -1;
        if (rb !== null) return 1;
        return n(b.obtained_marks) - n(a.obtained_marks);
      }
      return (a.roll ?? Number.MAX_SAFE_INTEGER) - (b.roll ?? Number.MAX_SAFE_INTEGER);
    });
  }, [scoped, search, outcome, sort, sectionId]);

  const publish = async () => {
    if (!exam) return;
    setPublishing(true);
    try {
      await apiClient.publishExam(exam.id);
      setConfirming(false);
      await data.reloadExams();
      await load();
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not publish these results.')));
      setConfirming(false);
    } finally {
      setPublishing(false);
    }
  };

  if (data.exams.length === 0) {
    return <EmptyCard>{t('No exams yet.')}</EmptyCard>;
  }

  const isPublished = exam?.status === 'published';
  // The Qawmi method has no GPA, so its sheet has no GPA column.
  const isGpa = current?.method !== 'division';
  const scaleLabel = current
    ? lang === 'bn' ? current.scale_name_bn || current.scale_name : current.scale_name
    : '';
  const manyStreams = new Set(sessionExams.map((e) => e.stream)).size > 1;
  const sectionLabel = (s: { name: string; name_bn: string }) => (lang === 'bn' ? s.name_bn || s.name : s.name);

  return (
    <div className="space-y-3">
      {/* ── What to look at ─────────────────────────────────────────────── */}
      <section className="space-y-2.5 rounded-xl border border-gray-200/80 bg-white p-3 shadow-sm print:hidden">
        {data.sessions.length > 1 && (
          <ChipRow label={t('Session')}>
            {data.sessions.map((s) => (
              <button
                key={s.id}
                type="button"
                aria-pressed={String(s.id) === sessionId}
                onClick={() => update({ session: String(s.id), exam: null, class: null, section: null })}
                className={chipCls(String(s.id) === sessionId)}
              >
                {s.name}
              </button>
            ))}
          </ChipRow>
        )}

        <ChipRow label={t('Exam')}>
          {sessionExams.length === 0 ? (
            <span className="text-[13px] text-gray-500">{t('No exams in this session.')}</span>
          ) : (
            sessionExams.map((e) => (
              <button
                key={e.id}
                type="button"
                aria-pressed={String(e.id) === examId}
                onClick={() => update({ exam: String(e.id), class: null, section: null })}
                className={chipCls(String(e.id) === examId)}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[e.status]}`} aria-hidden />
                {examLabel(e)}
                {manyStreams && e.stream_name && <span className="opacity-70">· {e.stream_name}</span>}
              </button>
            ))
          )}
        </ChipRow>

        {exam && (
          <ChipRow label={t('Class')}>
            {paperClasses.length === 0 ? (
              <span className="text-[13px] text-gray-500">{t('No papers scheduled yet.')}</span>
            ) : (
              paperClasses.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  aria-pressed={String(c.id) === classId}
                  onClick={() => update({ class: String(c.id), section: null })}
                  className={chipCls(String(c.id) === classId)}
                >
                  {classLabel(c)}
                </button>
              ))
            )}
          </ChipRow>
        )}

        {sections.length > 0 && (
          <ChipRow label={t('Section')}>
            <button
              type="button"
              aria-pressed={!sectionId}
              onClick={() => update({ section: null })}
              className={chipCls(!sectionId)}
            >
              {t('All sections')}
            </button>
            {sections.map((s) => (
              <button
                key={s.id}
                type="button"
                aria-pressed={String(s.id) === sectionId}
                onClick={() => update({ section: String(s.id) })}
                className={chipCls(String(s.id) === sectionId)}
              >
                {sectionLabel(s)}
              </button>
            ))}
          </ChipRow>
        )}

        {exam && (
          <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2.5">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                isPublished ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-800'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${isPublished ? 'bg-green-500' : 'bg-amber-500'}`} aria-hidden />
              {isPublished
                ? t('Published — students can see these results.')
                : t('Not published — students cannot see these marks yet.')}
            </span>
            {scaleLabel && (
              <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
                {scaleLabel}
              </span>
            )}
            {mayPublish && !isPublished && (
              <button type="button" onClick={() => setConfirming(true)} className={`${btnPrimary} ml-auto`}>
                {t('Publish results')}
              </button>
            )}
          </div>
        )}
      </section>

      {/* The heading a printed sheet needs and a screen does not. */}
      <div className="hidden print:block">
        <h2 className="text-lg font-bold">
          {examLabel(exam)} · {classLabel(chosenClass)}
          {chosenSection ? ` · ${sectionLabel(chosenSection)}` : ''}
        </h2>
      </div>

      {error && <FormError message={error} />}

      {current && scoped.length > 0 && (
        <div className="grid grid-cols-3 gap-2 lg:grid-cols-6">
          <Stat
            label={t('Examinees')}
            value={stats.examinees}
            hint={stats.notEntered ? `${stats.notEntered} ${t('not entered')}` : undefined}
          />
          <Stat label={t('Passed')} value={stats.passed} tone="green" />
          <Stat label={t('Failed')} value={stats.failed} tone={stats.failed ? 'red' : undefined} />
          <Stat label={t('Pass rate')} value={`${stats.passRate}%`} />
          <Stat label={t('Highest')} value={`${fmt(stats.highest)}%`} />
          <Stat label={t('Average')} value={`${fmt(stats.average)}%`} />
        </div>
      )}

      {current && scoped.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 print:hidden">
          <div className="relative w-full sm:w-64">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('Search in this sheet')}
              aria-label={t('Search in this sheet')}
              className={`${inputCls} pl-9 sm:pl-9`}
            />
          </div>
          <Segmented
            value={outcome}
            onChange={setOutcome}
            options={[
              { value: 'all', label: t('Everyone') },
              { value: 'passed', label: t('Passed') },
              { value: 'failed', label: t('Failed') },
            ]}
          />
          <Segmented
            value={sort}
            onChange={setSort}
            options={[
              { value: 'roll', label: t('By roll') },
              { value: 'rank', label: t('By rank') },
            ]}
          />
          <button type="button" onClick={() => window.print()} className={`${btnSecondary} sm:ml-auto`}>
            <PrintIcon />
            {t('Print')}
          </button>
        </div>
      )}

      {loading && !current && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

      {current && scoped.length === 0 && (
        <EmptyCard>{t('No students are enrolled in this class.')}</EmptyCard>
      )}

      {current && scoped.length > 0 && shown.length === 0 && (
        <EmptyCard>{t('No students match this filter.')}</EmptyCard>
      )}

      {/* `print:overflow-visible` on the table's own container: a scroll
          container prints what is on screen and clips the rest, so a class with
          eight subjects lost Total, GPA and the rank off the right-hand edge of
          the paper. */}
      {current && shown.length > 0 && (
        <div className="scroll-x rounded-xl border border-gray-200/80 bg-white shadow-sm print:overflow-visible print:border-0 print:shadow-none">
          <table className="min-w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-xs text-gray-500">
                <th className="sticky left-0 z-10 min-w-[12rem] bg-gray-50 px-3 py-2 text-left font-medium">
                  {t('Roll')} · {t('Student')}
                </th>
                {subjectColumns.map((column) => (
                  <th key={column.id} className="px-2 py-2 text-center font-medium">
                    <span className="block whitespace-nowrap text-gray-700">{column.name}</span>
                    <span className="block text-[10px] font-normal text-gray-400">{column.full}</span>
                  </th>
                ))}
                <th className="border-l border-gray-200 px-2 py-2 text-center font-medium">{t('Total')}</th>
                <th className="px-2 py-2 text-center font-medium">%</th>
                {isGpa && <th className="px-2 py-2 text-center font-medium">{t('GPA')}</th>}
                <th className="px-2 py-2 text-center font-medium">{t('Grade')}</th>
                <th className="whitespace-nowrap px-2 py-2 text-center font-medium">{t('Class rank')}</th>
                {sections.length > 0 && (
                  <th className="whitespace-nowrap px-2 py-2 text-center font-medium">{t('Section rank')}</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {shown.map((row) => {
                const hasMarks = Object.keys(row.marks).length > 0;
                const name = lang === 'bn' ? row.student_name_bn || row.student_name : row.student_name;
                return (
                  <tr
                    key={row.enrolment}
                    onClick={() => onOpenStudent(row.student, Number(examId))}
                    className="group cursor-pointer transition-colors hover:bg-blue-50/60"
                  >
                    <th
                      scope="row"
                      className="sticky left-0 z-10 bg-white px-3 py-1.5 text-left font-normal group-hover:bg-blue-50"
                    >
                      <span className="flex items-center gap-2.5">
                        <span className="w-6 shrink-0 text-right font-mono text-xs text-gray-400">
                          {row.roll ?? '—'}
                        </span>
                        <span className="min-w-0">
                          <span className="block max-w-[14rem] truncate font-medium text-gray-900 group-hover:text-blue-700">
                            {name}
                          </span>
                          <span className="block truncate font-mono text-[11px] text-gray-400">
                            {row.student_code}
                            {!sectionId && row.section_name
                              ? ` · ${lang === 'bn' ? row.section_name_bn || row.section_name : row.section_name}`
                              : ''}
                          </span>
                        </span>
                      </span>
                    </th>
                    {subjectColumns.map((column) => {
                      const cell = row.marks[String(column.id)];
                      const failed = !!cell && (cell.is_absent || n(cell.total) < column.pass);
                      return (
                        <td
                          key={column.id}
                          className={`px-2 py-1.5 text-center tabular-nums ${
                            !cell ? 'text-gray-300' : failed ? 'font-medium text-red-600' : 'text-gray-900'
                          }`}
                        >
                          {!cell ? '—' : cell.is_absent ? t('Absent') : fmt(cell.total)}
                        </td>
                      );
                    })}
                    <td className="whitespace-nowrap border-l border-gray-100 px-2 py-1.5 text-center font-semibold tabular-nums text-gray-900">
                      {fmt(row.obtained_marks)}
                      <span className="font-normal text-gray-400">/{fmt(row.total_marks)}</span>
                    </td>
                    <td className="px-2 py-1.5 text-center tabular-nums text-gray-700">
                      {hasMarks ? `${fmt(row.percentage)}%` : '—'}
                    </td>
                    {isGpa && (
                      <td className="px-2 py-1.5 text-center tabular-nums text-gray-700">
                        {hasMarks && row.is_passed && row.gpa !== null ? fmt(row.gpa) : '—'}
                      </td>
                    )}
                    <td className="px-2 py-1.5 text-center">
                      {hasMarks ? (
                        <GradeBadge grade={row.grade} label={lang === 'bn' ? row.grade_bn : row.grade} passed={row.is_passed} />
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <RankBadge rank={row.rank_in_class} />
                    </td>
                    {sections.length > 0 && (
                      <td className="px-2 py-1.5 text-center">
                        <RankBadge rank={row.rank_in_section} />
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <BaseModal
        isOpen={confirming}
        onClose={() => setConfirming(false)}
        title={t('Publish results')}
        maxWidth="md"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setConfirming(false)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void publish()}
              disabled={publishing}
              className={`${btnPrimary} flex-1`}
            >
              {publishing ? t('Publishing…') : t('Publish')}
            </button>
          </div>
        }
      >
        <p className="text-sm text-gray-700">
          {t('Publishing makes these results visible to students, and marks can no longer be changed afterwards.')}
        </p>
        {exam && <p className="mt-2 text-sm font-medium text-gray-900">{examLabel(exam)}</p>}
      </BaseModal>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Student results
// ─────────────────────────────────────────────────────────────────────────────

function StudentResults({ studentId, focusExam }: { studentId: string; focusExam: string }) {
  const { t, lang } = useT();
  const { user, branches, activeBranchId } = useAuth();
  const [report, setReport] = useState<StudentReport | null>(null);
  const [failure, setFailure] = useState<{ id: string; message: string } | null>(null);
  /** Exam id → open or closed, once the reader has touched it. Untouched, the
   *  exam they came from (or else the newest) is open. */
  const [toggled, setToggled] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!studentId) return;
    const timer = setTimeout(() => {
      apiClient
        .getStudentReport(Number(studentId))
        .then((next) => {
          setReport(next);
          setFailure(null);
        })
        .catch((err) =>
          setFailure({
            id: studentId,
            message: apiErrorText(err, t, t('Could not load this student’s results.')),
          }),
        );
    }, 0);
    return () => clearTimeout(timer);
  }, [studentId, t]);

  if (!studentId) {
    return (
      <EmptyCard>
        <SearchIcon className="mx-auto mb-2 h-6 w-6 text-gray-300" />
        {t('Search for a student above to see every result they have.')}
      </EmptyCard>
    );
  }
  if (failure && failure.id === studentId) return <FormError message={failure.message} />;

  const mine = report && String(report.student) === studentId ? report : null;
  if (!mine) return <p className="text-sm text-gray-400">{t('Loading…')}</p>;

  const institution =
    user?.branch_name
    || (() => {
      const branch = branches.find((b) => b.id === activeBranchId);
      return branch ? branch.name_bn || branch.name : '';
    })();
  const name = lang === 'bn' ? mine.student_name_bn || mine.student_name : mine.student_name;
  const latest = mine.exams[0];

  // Newest session first, exams inside it newest first — the order they came.
  const groups: { session: string; lines: StudentReportExam[] }[] = [];
  for (const line of mine.exams) {
    const last = groups[groups.length - 1];
    if (last && last.session === line.session_name) last.lines.push(line);
    else groups.push({ session: line.session_name, lines: [line] });
  }

  return (
    <div className="space-y-3">
      <section className="flex items-center gap-3 rounded-xl border border-gray-200/80 bg-white p-4 shadow-sm">
        <Avatar name={name} large />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-gray-900">{name}</h2>
          <p className="truncate text-xs text-gray-500">
            <span className="font-mono">{mine.student_code}</span>
            {latest &&
              ` · ${lang === 'bn' ? latest.class_name_bn || latest.class_name : latest.class_name}${
                latest.section_name
                  ? ` ${lang === 'bn' ? latest.section_name_bn || latest.section_name : latest.section_name}`
                  : ''
              }${latest.roll !== null ? ` · ${t('Roll')} ${latest.roll}` : ''}`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[11px] font-medium text-gray-500">{t('Exams')}</p>
          <p className="text-lg font-semibold tabular-nums text-gray-900">{mine.exams.length}</p>
        </div>
      </section>

      {mine.exams.length === 0 && <EmptyCard>{t('This student has no results yet.')}</EmptyCard>}

      {groups.map((group) => (
        <div key={group.session} className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
            {t('Session')} {group.session}
          </h3>
          {group.lines.map((line) => {
            const index = mine.exams.indexOf(line);
            const expanded =
              toggled[line.exam] ?? (focusExam ? String(line.exam) === focusExam : index === 0);
            return (
              <ExamCard
                key={line.exam}
                line={line}
                expanded={expanded}
                onToggle={() => setToggled((prev) => ({ ...prev, [line.exam]: !expanded }))}
                onPrint={() => printMarksheet({ t, lang, institution, report: mine, line })}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

function ExamCard({
  line,
  expanded,
  onToggle,
  onPrint,
}: {
  line: StudentReportExam;
  expanded: boolean;
  onToggle: () => void;
  onPrint: () => void;
}) {
  const { t, lang } = useT();
  const examName = lang === 'bn' ? line.exam_name_bn || line.exam_name : line.exam_name;
  const className = lang === 'bn' ? line.class_name_bn || line.class_name : line.class_name;
  const sectionName = lang === 'bn' ? line.section_name_bn || line.section_name : line.section_name;
  const typeLabel = t(EXAM_TYPES.find((x) => x.value === line.exam_type)?.label ?? '');
  const hasPractical = line.subjects.some((s) => s.practical_obtained !== null && s.practical_obtained !== undefined);

  return (
    <article className="overflow-hidden rounded-xl border border-gray-200/80 bg-white shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50/80"
      >
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 text-sm font-semibold text-gray-900">
            <span className="truncate">{examName}</span>
            {line.status !== 'published' && (
              <span className="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                {t('Not published')}
              </span>
            )}
          </p>
          <p className="truncate text-xs text-gray-500">
            {[typeLabel, `${className}${sectionName ? ` ${sectionName}` : ''}`, line.starts_on]
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="hidden text-right sm:block">
            <p className="text-sm font-semibold tabular-nums text-gray-900">{fmt(line.percentage)}%</p>
            <p className="text-[11px] text-gray-500">
              {line.method === 'division'
                ? lang === 'bn'
                  ? line.scale_name_bn || line.scale_name
                  : line.scale_name
                : `${t('GPA')} ${line.is_passed && line.gpa !== null ? fmt(line.gpa) : '—'}`}
            </p>
          </div>
          <GradeBadge grade={line.grade} label={lang === 'bn' ? line.grade_bn : line.grade} passed={line.is_passed} />
          <svg
            className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden
          >
            <path
              fillRule="evenodd"
              d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      </button>

      <dl className="grid grid-cols-2 gap-px border-t border-gray-100 bg-gray-100 sm:grid-cols-4">
        <Fact label={t('Obtained')} value={`${fmt(line.obtained_marks)} / ${fmt(line.total_marks)}`} />
        <Fact label={t('Percentage')} value={`${fmt(line.percentage)}%`} />
        <Fact
          label={t('Class rank')}
          value={line.rank_in_class ? `${line.rank_in_class} / ${line.class_size}` : '—'}
        />
        <Fact label={t('Section rank')} value={line.section && line.rank_in_section ? String(line.rank_in_section) : '—'} />
      </dl>

      {expanded && (
        <div className="border-t border-gray-100">
          <div className="scroll-x">
            <table className="min-w-full text-[13px]">
              <thead>
                <tr className="bg-gray-50 text-xs text-gray-500">
                  <th className="px-4 py-2 text-left font-medium">{t('Subject')}</th>
                  <th className="px-2 py-2 text-center font-medium">{t('Full marks')}</th>
                  <th className="px-2 py-2 text-center font-medium">{t('Pass marks')}</th>
                  {hasPractical && <th className="px-2 py-2 text-center font-medium">{t('Practical')}</th>}
                  <th className="px-2 py-2 text-center font-medium">{t('Obtained')}</th>
                  <th className="px-2 py-2 text-center font-medium">{t('Grade')}</th>
                  <th className="px-4 py-2 text-right font-medium">{t('Result')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {line.subjects.map((subject) => (
                  <tr key={subject.subject} className={subject.is_passed ? '' : 'bg-red-50/40'}>
                    <td className="px-4 py-2 text-gray-900">
                      {lang === 'bn' ? subject.subject_name_bn || subject.subject_name : subject.subject_name}
                    </td>
                    <td className="px-2 py-2 text-center tabular-nums text-gray-500">{fmt(subject.full_marks)}</td>
                    <td className="px-2 py-2 text-center tabular-nums text-gray-500">{fmt(subject.pass_marks)}</td>
                    {hasPractical && (
                      <td className="px-2 py-2 text-center tabular-nums text-gray-500">
                        {subject.practical_obtained === null ? '—' : fmt(subject.practical_obtained)}
                      </td>
                    )}
                    <td
                      className={`px-2 py-2 text-center font-semibold tabular-nums ${
                        subject.is_passed ? 'text-gray-900' : 'text-red-600'
                      }`}
                    >
                      {subject.is_absent ? t('Absent') : fmt(subject.total)}
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-center text-xs font-semibold">
                      {subject.grade ? (
                        <span className={subject.is_passed ? 'text-gray-700' : 'text-red-600'}>
                          {lang === 'bn' ? subject.grade_bn || subject.grade : subject.grade}
                          {line.method !== 'division' && subject.point !== null && subject.point !== undefined && (
                            <span className="ml-1 font-normal text-gray-400">{fmt(subject.point)}</span>
                          )}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-2 text-right text-xs font-medium">
                      {subject.is_passed ? (
                        <span className="text-green-700">{t('Passed')}</span>
                      ) : (
                        <span className="text-red-600">{subject.is_absent ? t('Absent') : t('Failed')}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 px-4 py-2.5">
            {line.failed_subjects.length > 0 ? (
              <p className="text-xs text-red-700">
                {t('Failed subjects')}: {line.failed_subjects.join(', ')}
              </p>
            ) : (
              <span />
            )}
            <button type="button" onClick={onPrint} className={btnSecondary}>
              <PrintIcon />
              {t('Print marksheet')}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

/**
 * One exam's marksheet, in a window of its own, sent to the printer.
 *
 * A separate document rather than `window.print()` on the dashboard: the
 * marksheet is an A4 page with a letterhead and signature lines, not a card
 * with the app's chrome hidden. The dashboard's own stylesheets are copied in
 * so the Bangla font is the same one the screen uses.
 */
function printMarksheet({
  t,
  lang,
  institution,
  report,
  line,
}: {
  t: Translate;
  lang: string;
  institution: string;
  report: StudentReport;
  line: StudentReportExam;
}) {
  const esc = (value: unknown) =>
    String(value ?? '').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const bn = lang === 'bn';
  const name = bn ? report.student_name_bn || report.student_name : report.student_name;
  const examName = bn ? line.exam_name_bn || line.exam_name : line.exam_name;
  const className = bn ? line.class_name_bn || line.class_name : line.class_name;
  const sectionName = bn ? line.section_name_bn || line.section_name : line.section_name;
  const grade = bn ? line.grade_bn : line.grade;

  const rows = line.subjects
    .map(
      (s) => `<tr${s.is_passed ? '' : ' class="fail"'}>
        <td>${esc(bn ? s.subject_name_bn || s.subject_name : s.subject_name)}</td>
        <td>${esc(fmt(s.full_marks))}</td>
        <td>${esc(fmt(s.pass_marks))}</td>
        <td>${s.is_absent ? esc(t('Absent')) : esc(fmt(s.total))}</td>
        <td>${esc(bn ? s.grade_bn || s.grade || '' : s.grade || '')}</td>
      </tr>`,
    )
    .join('');

  const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
    .map((node) => node.outerHTML)
    .join('');

  const win = window.open('', '_blank', 'width=820,height=1000');
  if (!win) return;
  win.document.write(`<!doctype html><html><head><meta charset="utf-8">
<title>${esc(t('Marksheet'))} — ${esc(name)}</title>${styles}
<style>
  body { margin: 0; padding: 32px; background: #fff; color: #111827; }
  .sheet { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0; text-align: center; }
  h2 { font-size: 15px; margin: 6px 0 22px; text-align: center; font-weight: 600; color: #374151; }
  .meta { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; font-size: 13px; margin-bottom: 16px; }
  .meta b { font-weight: 600; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { border: 1px solid #d1d5db; padding: 6px 10px; text-align: center; }
  th:first-child, td:first-child { text-align: left; }
  thead th { background: #f3f4f6; }
  tr.fail td { color: #b91c1c; }
  .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 16px; }
  .summary div { border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px 10px; }
  .summary span { display: block; font-size: 11px; color: #6b7280; }
  .summary strong { font-size: 15px; }
  .sign { display: flex; justify-content: space-between; margin-top: 72px; font-size: 12px; color: #374151; }
  .sign span { border-top: 1px solid #9ca3af; padding-top: 6px; min-width: 160px; text-align: center; }
  @page { size: A4; margin: 14mm; }
</style></head><body><div class="sheet">
  <h1>${esc(institution)}</h1>
  <h2>${esc(t('Marksheet'))} · ${esc(examName)}</h2>
  <div class="meta">
    <div><b>${esc(t('Student'))}:</b> ${esc(name)}</div>
    <div><b>ID:</b> ${esc(report.student_code)}</div>
    <div><b>${esc(t('Class'))}:</b> ${esc(className)}${sectionName ? ` · ${esc(sectionName)}` : ''}</div>
    <div><b>${esc(t('Roll'))}:</b> ${esc(line.roll ?? '—')}</div>
    <div><b>${esc(t('Session'))}:</b> ${esc(line.session_name)}</div>
    <div><b>${esc(t('Result'))}:</b> ${esc(line.is_passed ? t('Passed') : t('Failed'))}</div>
  </div>
  <table>
    <thead><tr><th>${esc(t('Subject'))}</th><th>${esc(t('Full marks'))}</th><th>${esc(t('Pass marks'))}</th><th>${esc(t('Obtained'))}</th><th>${esc(t('Grade'))}</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>
  <div class="summary">
    <div><span>${esc(t('Total'))}</span><strong>${esc(fmt(line.obtained_marks))} / ${esc(fmt(line.total_marks))}</strong></div>
    <div><span>${esc(t('Percentage'))}</span><strong>${esc(fmt(line.percentage))}%</strong></div>
    ${line.method === 'division'
      ? `<div><span>${esc(t('Grade'))}</span><strong>${esc(grade)}</strong></div>`
      : `<div><span>${esc(t('GPA'))} · ${esc(t('Grade'))}</span><strong>${esc(line.is_passed && line.gpa !== null ? fmt(line.gpa) : '—')} · ${esc(grade)}</strong></div>`}
    <div><span>${esc(t('Class rank'))}</span><strong>${esc(line.rank_in_class ? `${line.rank_in_class} / ${line.class_size}` : '—')}</strong></div>
  </div>
  <div class="sign"><span>${esc(t('Class teacher'))}</span><span>${esc(t('Principal'))}</span></div>
</div></body></html>`);
  win.document.close();
  win.focus();
  // A beat for the copied fonts to load, or the first page prints in a fallback.
  setTimeout(() => win.print(), 400);
}

// ─────────────────────────────────────────────────────────────────────────────
// Small pieces
// ─────────────────────────────────────────────────────────────────────────────

function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3">
      <span className="shrink-0 text-xs font-medium text-gray-500 sm:w-20">{label}</span>
      {/* Scrolls inside itself, so twelve classes never widen the page. */}
      <div className="scroll-x -mx-1 min-w-0 flex-1 px-1">
        <div className="flex w-max gap-1.5">{children}</div>
      </div>
    </div>
  );
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="inline-flex h-8 items-center gap-0.5 rounded-lg bg-gray-100 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={`h-7 whitespace-nowrap rounded-md px-2.5 text-xs font-medium transition-all ${
            value === option.value
              ? 'bg-white text-gray-900 shadow-sm ring-1 ring-gray-900/5'
              : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: 'green' | 'red';
}) {
  return (
    <div className="rounded-lg border border-gray-200/80 bg-white px-3 py-2 shadow-sm">
      <p className="truncate text-[11px] font-medium text-gray-500">{label}</p>
      <p
        className={`text-lg font-semibold leading-tight tabular-nums ${
          tone === 'green' ? 'text-green-700' : tone === 'red' ? 'text-red-600' : 'text-gray-900'
        }`}
      >
        {value}
      </p>
      {hint && <p className="truncate text-[11px] text-amber-700">{hint}</p>}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white px-4 py-2">
      <dt className="text-[11px] text-gray-500">{label}</dt>
      <dd className="text-[13px] font-semibold tabular-nums text-gray-900">{value}</dd>
    </div>
  );
}

/** Colour follows the English grade, whichever language the label is in. */
function GradeBadge({ grade, label, passed }: { grade: string; label: string; passed: boolean }) {
  const tone = !passed
    ? 'bg-red-50 text-red-700 ring-red-600/20'
    : grade === 'A+'
      ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20'
      : grade.startsWith('A')
        ? 'bg-green-50 text-green-700 ring-green-600/20'
        : grade === 'B'
          ? 'bg-blue-50 text-blue-700 ring-blue-600/20'
          : 'bg-amber-50 text-amber-800 ring-amber-600/20';
  return (
    <span
      className={`inline-flex min-w-[2.25rem] justify-center rounded-md px-1.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${tone}`}
    >
      {label}
    </span>
  );
}

/** First, second and third get a colour; everyone else is a number. */
function RankBadge({ rank }: { rank: number | null }) {
  if (rank === null) return <span className="text-gray-300">—</span>;
  const tone =
    rank === 1
      ? 'bg-amber-100 text-amber-800'
      : rank === 2
        ? 'bg-slate-200 text-slate-700'
        : rank === 3
          ? 'bg-orange-100 text-orange-800'
          : 'text-gray-700';
  return (
    <span
      className={`inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded-full px-1.5 text-xs font-semibold tabular-nums ${tone}`}
    >
      {rank}
    </span>
  );
}

function Avatar({ name, photo, large = false }: { name: string; photo?: string | null; large?: boolean }) {
  const size = large ? 'h-12 w-12 text-base' : 'h-8 w-8 text-xs';
  if (photo) {
    return <img src={photo} alt="" className={`${size} shrink-0 rounded-full object-cover ring-1 ring-gray-900/5`} />;
  }
  return (
    <span
      className={`${size} flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 font-semibold text-white`}
    >
      {(name || '?').trim().slice(0, 1).toUpperCase()}
    </span>
  );
}

function EmptyCard({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
      {children}
    </div>
  );
}

function SearchIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 10.5a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z" />
    </svg>
  );
}

function PrintIcon() {
  return (
    <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24" aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6 9V3h12v6M6 18H4a1 1 0 01-1-1v-6a2 2 0 012-2h14a2 2 0 012 2v6a1 1 0 01-1 1h-2M6 14h12v7H6v-7z"
      />
    </svg>
  );
}
