import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../lib/api';
import type { AcademicClass, Exam, Session, Stream, Subject, Teacher } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import ExamsTab from '../components/exams/ExamsTab';
import MarksEntryTab from '../components/exams/MarksEntryTab';
import ResultsTab from '../components/exams/ResultsTab';
import type { ExamsData } from '../components/exams/shared';

/**
 * Examinations — the exam and its schedule, marks entry, and results.
 *
 * The three tabs sit behind **two different permissions**, which is the point
 * of `docs/02` §2.1's split: a teacher holds `marks.enter` and reaches the
 * middle tab without ever holding `exams.create`; only a principal holds
 * `exams.publish` and sees the Publish button on the third. So the tab strip is
 * built from what the person actually holds rather than shown whole and
 * refused on arrival.
 *
 * Sessions, streams, classes, teachers and the exam list are fetched once here.
 * Subjects are per class and cached on demand — the schedule form and the marks
 * grid ask for the same list.
 */

type Tab = 'exams' | 'marks' | 'results';

export default function ExamsPage() {
  const { t } = useT();
  const { can, canView } = usePermissions();
  const { activeBranchId } = useAuth();

  const mayViewExams = canView('exams');
  const mayEnterMarks = can('marks', 'enter') || can('marks', 'update') || can('marks', 'view');

  // `useTabParam` needs the list of tabs this person may actually open, so a
  // stale `?tab=marks` for someone without `marks.*` falls back rather than
  // rendering a tab they cannot use.
  const available: Tab[] = [
    ...(mayViewExams ? (['exams'] as Tab[]) : []),
    ...(mayEnterMarks ? (['marks'] as Tab[]) : []),
    ...(mayViewExams ? (['results'] as Tab[]) : []),
  ];
  const [tab, setTab] = useTabParam<Tab>(available.length > 0 ? available : ['exams'], available[0] ?? 'exams');

  const [sessions, setSessions] = useState<Session[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [exams, setExams] = useState<Exam[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);

  const fetchedSubjects = useRef(new Set<string>());

  const reloadExams = useCallback(
    () =>
      apiClient
        .listAll<Exam>('/exams/', '?ordering=-starts_on')
        .then(setExams)
        .catch(() => setExams([])),
    [],
  );

  const loadSubjects = useCallback((classId: string) => {
    if (!classId || fetchedSubjects.current.has(classId)) return;
    fetchedSubjects.current.add(classId);
    void apiClient
      .listAll<Subject>('/subjects/', `?academic_class=${classId}&is_active=true`)
      .then((rows) =>
        setSubjects((prev) => [...prev.filter((s) => String(s.academic_class) !== classId), ...rows]),
      )
      .catch(() => undefined);
  }, []);

  const subjectsFor = useCallback(
    (classId: string) => subjects.filter((s) => String(s.academic_class) === classId),
    [subjects],
  );

  useEffect(() => {
    if (available.length === 0) return;
    void apiClient.listSessions(activeBranchId).then(setSessions).catch(() => setSessions([]));
    void apiClient.listStreams(activeBranchId).then(setStreams).catch(() => setStreams([]));
    void apiClient
      .listAll<AcademicClass>('/classes/', '?is_active=true')
      .then(setClasses)
      .catch(() => setClasses([]));
    // Invigilators. A missing `teachers.view` leaves that picker empty rather
    // than breaking the schedule form.
    void apiClient
      .listAll<Teacher>('/teachers/', '?is_active=true')
      .then(setTeachers)
      .catch(() => setTeachers([]));
    void reloadExams();
    // `available` is derived from permissions, which do not change while the
    // page is mounted; its length standing in for it keeps the dependency
    // list honest without re-fetching on every render.
  }, [available.length, activeBranchId, reloadExams]);

  if (available.length === 0) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Exams')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const data: ExamsData = {
    sessions,
    streams,
    classes,
    teachers,
    exams,
    reloadExams,
    subjectsFor,
    loadSubjects,
  };

  const labels: Record<Tab, string> = {
    exams: t('Exams'),
    marks: t('Marks entry'),
    results: t('Results'),
  };
  const tabs: TabDef<Tab>[] = available.map((key) => ({ key, label: labels[key] }));

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Exams')}</h1>
      </header>

      <TabStrip tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'exams' && <ExamsTab data={data} />}
      {tab === 'marks' && <MarksEntryTab data={data} />}
      {tab === 'results' && <ResultsTab data={data} />}
    </div>
  );
}
