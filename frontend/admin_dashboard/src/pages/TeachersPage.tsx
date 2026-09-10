import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { AcademicClass, Session, Stream, Teacher } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import TeachersTab from '../components/staff/TeachersTab';
import AssignmentsTab from '../components/staff/AssignmentsTab';

/**
 * Teachers — the roster, and which classes each one covers.
 *
 * Its own top-level section rather than a tab under a combined "Staff", which
 * is how the data already sees it: `Teacher` and `Employee` are separate models
 * off a shared abstract base (`docs/08` D5), and `docs/02` §2.1 keeps
 * `teachers` and `employees` as separate permission resources so an office
 * manager can maintain the non-teaching roster without ever seeing a teacher's
 * salary. Merging them in the sidebar hid a distinction the rest of the system
 * makes everywhere.
 *
 * Assignments lives here and not under Academics because it is about a
 * *person's* work — and because it is the screen that decides what a teacher
 * can reach (`docs/08` D6), which is a fact about the teacher.
 */

type Tab = 'list' | 'assignments';

const TABS: Tab[] = ['list', 'assignments'];

export default function TeachersPage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const { activeBranchId } = useAuth();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'list');

  const [streams, setStreams] = useState<Stream[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);

  const maySeeTeachers = canView('teachers');
  const maySeeAssignments = canView('academics');

  useEffect(() => {
    if (maySeeTeachers) {
      void apiClient.listStreams(activeBranchId).then(setStreams).catch(() => setStreams([]));
    }
    if (maySeeAssignments) {
      void apiClient.listSessions(activeBranchId).then(setSessions).catch(() => setSessions([]));
      void apiClient
        .listAll<AcademicClass>('/classes/', '?is_active=true')
        .then(setClasses)
        .catch(() => setClasses([]));
      // The whole teacher list, because the assignment board's every card is a
      // drop target over it — twenty selects each fetching their own options is
      // twenty requests for one list.
      void apiClient
        .listAll<Teacher>('/teachers/', '?is_active=true')
        .then(setTeachers)
        .catch(() => setTeachers([]));
    }
  }, [activeBranchId, maySeeTeachers, maySeeAssignments]);

  if (!maySeeTeachers && !maySeeAssignments) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Teachers')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    ...(maySeeTeachers ? ([{ key: 'list', label: t('Teachers') }] as TabDef<Tab>[]) : []),
    ...(maySeeAssignments ? ([{ key: 'assignments', label: t('Assignments') }] as TabDef<Tab>[]) : []),
  ];

  // Somebody holding only `academics` lands on Assignments rather than on an
  // empty roster they cannot fill.
  const active = tabs.some((x) => x.key === tab) ? tab : tabs[0].key;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Teachers')}</h1>
      </header>

      {tabs.length > 1 && <TabStrip tabs={tabs} active={active} onChange={setTab} />}

      {active === 'list' && maySeeTeachers && <TeachersTab streams={streams} />}
      {active === 'assignments' && maySeeAssignments && (
        <AssignmentsTab sessions={sessions} classes={classes} teachers={teachers} />
      )}
    </div>
  );
}
