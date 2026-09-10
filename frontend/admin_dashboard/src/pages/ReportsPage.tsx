import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { AcademicClass, Section, Session, Stream } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import { thisMonth } from '../lib/period';
import type { Period } from '../lib/period';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import StudentsReport from '../components/reports/StudentsReport';
import AttendanceReport from '../components/reports/AttendanceReport';
import FeesReport from '../components/reports/FeesReport';
import FinanceReport from '../components/reports/FinanceReport';
import ExamsReport from '../components/reports/ExamsReport';

/**
 * Reports — one screen, five tabs (`docs/02` §4.8).
 *
 * **Every figure here is read from the module's own list endpoints and summed
 * on the client.** There is no `reports` app in V1 (`CLAUDE.md` §2) and no
 * export endpoint anywhere in the API, so a report is a view over the same rows
 * the module screens show. That is the right default — a report that queried
 * its own tables would be a second definition of "collected this month" — but
 * it has a ceiling: `listAll` stops at 2,000 rows, and none of the list
 * endpoints has a date-RANGE filter, so the period is applied here.
 *
 * **The gate is `reports.view`, and export is `reports.export`.** Not the
 * module's own permission: an accountant reads the fee report because they hold
 * `reports.view`, and a person who may read one may read all of them — which is
 * why this is one screen rather than five buried in the modules.
 *
 * The lookups — sessions, classes, sections, streams — are fetched once here
 * and handed down. They are the same three pickers on four of the five tabs,
 * and they change once a year.
 */

type Tab = 'students' | 'attendance' | 'fees' | 'finance' | 'exams';

const TABS: Tab[] = ['students', 'attendance', 'fees', 'finance', 'exams'];

export default function ReportsPage() {
  const { t } = useT();
  const { can, canView } = usePermissions();
  const { user, activeBranchId } = useAuth();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'students');

  // One period for the whole screen: somebody comparing March's collection with
  // March's attendance should not have to set the month twice.
  const [period, setPeriod] = useState<Period>(thisMonth);

  const [sessions, setSessions] = useState<Session[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [sections, setSections] = useState<Section[]>([]);

  const maySee = canView('reports');
  const mayExport = can('reports', 'export');
  // The operator of SIES, whose `user.branch` is null — the only person the
  // cross-institution comparison exists for (`docs/08` D1).
  const isPlatformAdmin = user?.branch === null;

  useEffect(() => {
    if (!maySee) return;
    const timer = setTimeout(() => {
      void apiClient.listSessions(activeBranchId).then(setSessions).catch(() => setSessions([]));
      void apiClient.listStreams(activeBranchId).then(setStreams).catch(() => setStreams([]));
      void apiClient
        .listAll<AcademicClass>('/classes/', '?is_active=true')
        .then(setClasses)
        .catch(() => setClasses([]));
      void apiClient
        .listAll<Section>('/sections/', '?is_active=true')
        .then(setSections)
        .catch(() => setSections([]));
    }, 0);
    return () => clearTimeout(timer);
  }, [activeBranchId, maySee]);

  if (!maySee) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Reports')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    { key: 'students', label: t('Students') },
    { key: 'attendance', label: t('Attendance') },
    { key: 'fees', label: t('Fees') },
    { key: 'finance', label: t('Accounts') },
    { key: 'exams', label: t('Exams') },
  ];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Reports')}</h1>
        <p className="mt-1 text-sm text-gray-500">
          {t('What the institution looks like this month, from the records themselves.')}
        </p>
      </header>

      <TabStrip tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'students' && (
        <StudentsReport
          period={period}
          onPeriod={setPeriod}
          sessions={sessions}
          classes={classes}
          sections={sections}
          streams={streams}
          mayExport={mayExport}
        />
      )}
      {tab === 'attendance' && (
        <AttendanceReport
          period={period}
          sessions={sessions}
          classes={classes}
          mayExport={mayExport}
        />
      )}
      {tab === 'fees' && (
        <FeesReport period={period} onPeriod={setPeriod} sessions={sessions} mayExport={mayExport} />
      )}
      {tab === 'finance' && (
        <FinanceReport
          period={period}
          onPeriod={setPeriod}
          sessions={sessions}
          isPlatformAdmin={isPlatformAdmin}
          mayExport={mayExport}
        />
      )}
      {tab === 'exams' && <ExamsReport classes={classes} mayExport={mayExport} />}
    </div>
  );
}
