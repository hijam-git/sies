import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { AcademicClass, Session, Stream, Teacher } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import ClassesTab from '../components/academics/ClassesTab';
import SectionsTab from '../components/academics/SectionsTab';
import SubjectsTab from '../components/academics/SubjectsTab';
import RoutineTab from '../components/academics/RoutineTab';
import type { AcademicsData } from '../components/academics/shared';

/**
 * Academics — the frame the whole system hangs off: classes, their sections and
 * subjects, and the weekly routine.
 *
 * All four tabs sit behind the single `academics` permission, because `docs/02`
 * §2.1 puts them behind one checkbox: they are edited by the same person on the
 * same afternoon, and a separate tick for "may edit sections" is a box nobody
 * would ever set differently.
 *
 * Sessions, streams, teachers and classes are fetched once here and handed
 * down. Every tab needs at least two of them, and four tabs each fetching their
 * own would re-read a list that changes once a year on every tab switch.
 */

type Tab = 'classes' | 'sections' | 'subjects' | 'routine';

const TABS: Tab[] = ['classes', 'sections', 'subjects', 'routine'];

export default function AcademicsPage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const { activeBranchId } = useAuth();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'classes');

  const [sessions, setSessions] = useState<Session[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [classes, setClasses] = useState<AcademicClass[]>([]);

  const mayView = canView('academics');

  const reloadClasses = useCallback(
    () =>
      apiClient
        .listAll<AcademicClass>('/classes/', '?is_active=true')
        .then(setClasses)
        .catch(() => setClasses([])),
    [],
  );

  useEffect(() => {
    if (!mayView) return;
    void apiClient.listSessions(activeBranchId).then(setSessions).catch(() => setSessions([]));
    void apiClient.listStreams(activeBranchId).then(setStreams).catch(() => setStreams([]));
    // Teachers fill the class-teacher, in-charge and routine pickers. A missing
    // `teachers.view` is not a reason to break this screen — the pickers simply
    // come up empty, which is honest and still lets the classes be edited.
    void apiClient
      .listAll<Teacher>('/teachers/', '?is_active=true')
      .then(setTeachers)
      .catch(() => setTeachers([]));
    void reloadClasses();
  }, [mayView, activeBranchId, reloadClasses]);

  if (!mayView) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Academics')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const data: AcademicsData = { sessions, streams, teachers, classes, reloadClasses };

  const tabs: TabDef<Tab>[] = [
    { key: 'classes', label: t('Classes') },
    { key: 'sections', label: t('Sections') },
    { key: 'subjects', label: t('Subjects') },
    { key: 'routine', label: t('Routine') },
  ];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Academics')}</h1>
      </header>

      <TabStrip tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'classes' && <ClassesTab data={data} />}
      {tab === 'sections' && <SectionsTab data={data} />}
      {tab === 'subjects' && <SubjectsTab data={data} />}
      {tab === 'routine' && <RoutineTab data={data} />}
    </div>
  );
}
