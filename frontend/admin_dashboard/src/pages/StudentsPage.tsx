import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { AcademicClass, Section, Session, Stream } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import StudentsTab from '../components/students/StudentsTab';
import AdmissionsTab from '../components/students/AdmissionsTab';

/**
 * Students — the roll, and the applications that fill it.
 *
 * Two tabs and two permissions: `students` is the record of somebody already
 * here, `admissions` is the process of them arriving. An admission officer holds
 * the second and often not the third of `students`' actions, which is exactly
 * the separation `docs/02` §2.1 draws.
 *
 * Sessions, streams, classes and sections are fetched here and handed to both
 * tabs. Both need them — the roll to say which class a student is in, the
 * admission form to say which class they are applying to — and they change once
 * a year.
 */

type Tab = 'students' | 'admissions';

const TABS: Tab[] = ['students', 'admissions'];

export default function StudentsPage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const { activeBranchId } = useAuth();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'students');

  const [sessions, setSessions] = useState<Session[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [sections, setSections] = useState<Section[]>([]);

  const maySeeStudents = canView('students');
  const maySeeAdmissions = canView('admissions');

  useEffect(() => {
    if (!maySeeStudents && !maySeeAdmissions) return;
    void apiClient.listSessions(activeBranchId).then(setSessions).catch(() => setSessions([]));
    void apiClient.listStreams(activeBranchId).then(setStreams).catch(() => setStreams([]));
    // Both lists whole rather than per class: they are pickers and lookup maps,
    // and an admission officer without `academics.view` simply gets empty ones
    // rather than a screen that fails to load.
    void apiClient
      .listAll<AcademicClass>('/classes/', '?is_active=true')
      .then(setClasses)
      .catch(() => setClasses([]));
    void apiClient
      .listAll<Section>('/sections/', '?is_active=true')
      .then(setSections)
      .catch(() => setSections([]));
  }, [activeBranchId, maySeeStudents, maySeeAdmissions]);

  if (!maySeeStudents && !maySeeAdmissions) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Students')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    ...(maySeeStudents ? ([{ key: 'students', label: t('Students') }] as TabDef<Tab>[]) : []),
    ...(maySeeAdmissions ? ([{ key: 'admissions', label: t('Admissions') }] as TabDef<Tab>[]) : []),
  ];

  const active = tabs.some((x) => x.key === tab) ? tab : tabs[0].key;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Students')}</h1>
        <p className="mt-1 text-sm text-gray-500">
          {t('Who is on the roll, and who is applying to be.')}
        </p>
      </header>

      <TabStrip tabs={tabs} active={active} onChange={setTab} />

      {active === 'students' && maySeeStudents && (
        <StudentsTab streams={streams} classes={classes} sections={sections} sessions={sessions} />
      )}
      {active === 'admissions' && maySeeAdmissions && (
        <AdmissionsTab sessions={sessions} streams={streams} classes={classes} sections={sections} />
      )}
    </div>
  );
}
