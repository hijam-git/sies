import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { AcademicClass, Session, Stream, Teacher } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import TeachersTab from '../components/staff/TeachersTab';
import EmployeesTab from '../components/staff/EmployeesTab';
import AssignmentsTab from '../components/staff/AssignmentsTab';

/**
 * Staff — teachers, employees, and who teaches what.
 *
 * Three tabs and three different permissions, which is the point of `docs/02`
 * §2.1 keeping `teachers` and `employees` apart: an office manager may maintain
 * the non-teaching roster without ever seeing a teacher's salary. Assignments
 * sits under `academics`, because it edits the academic frame rather than a
 * person's record.
 */

type Tab = 'teachers' | 'employees' | 'assignments';

const TABS: Tab[] = ['teachers', 'employees', 'assignments'];

export default function StaffPage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const { activeBranchId } = useAuth();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'teachers');

  const [streams, setStreams] = useState<Stream[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);

  const maySeeTeachers = canView('teachers');
  const maySeeEmployees = canView('employees');
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
      // The whole teacher list, because the assignment screen's every row is a
      // picker over it — twenty selects each fetching their own options is
      // twenty requests for one list.
      void apiClient
        .listAll<Teacher>('/teachers/', '?is_active=true')
        .then(setTeachers)
        .catch(() => setTeachers([]));
    }
  }, [activeBranchId, maySeeTeachers, maySeeAssignments]);

  if (!maySeeTeachers && !maySeeEmployees && !maySeeAssignments) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Staff')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    ...(maySeeTeachers ? ([{ key: 'teachers', label: t('Teachers') }] as TabDef<Tab>[]) : []),
    ...(maySeeEmployees ? ([{ key: 'employees', label: t('Employees') }] as TabDef<Tab>[]) : []),
    ...(maySeeAssignments ? ([{ key: 'assignments', label: t('Assignments') }] as TabDef<Tab>[]) : []),
  ];

  // Somebody who holds only `employees` lands on the tab they actually have,
  // rather than on an empty Teachers panel they cannot fill.
  const active = tabs.some((x) => x.key === tab) ? tab : tabs[0].key;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Staff')}</h1>
        <p className="mt-1 text-sm text-gray-500">
          {t('Teachers, other employees, and which classes each teacher covers.')}
        </p>
      </header>

      <TabStrip tabs={tabs} active={active} onChange={setTab} />

      {active === 'teachers' && maySeeTeachers && <TeachersTab streams={streams} />}
      {active === 'employees' && maySeeEmployees && <EmployeesTab />}
      {active === 'assignments' && maySeeAssignments && (
        <AssignmentsTab sessions={sessions} classes={classes} teachers={teachers} />
      )}
    </div>
  );
}
