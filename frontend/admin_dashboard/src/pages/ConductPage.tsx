import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '../lib/api';
import type { AcademicClass, ReportTemplate, Section, Stream } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import ConductSheetTab from '../components/conduct/ConductSheetTab';
import ConductSetupTab from '../components/conduct/ConductSetupTab';

/**
 * Conduct — নামাজ, তিলাওয়াত, আদব (`docs/02` §4.10).
 *
 * Two tabs and two permissions. **The sheet is `conduct`** — the teacher's act
 * of observing — and **the setup is `settings`**, because deciding what the
 * institution observes belongs to the office. A teacher therefore sees one tab
 * and a principal sees both, which is the split the backend enforces anyway.
 *
 * The class list comes from `/classes/`, teacher-scoped on the server
 * (`docs/08` D6), so the restriction reads as a shorter list rather than as an
 * error on a class that should never have been offered.
 */

type Tab = 'sheet' | 'setup';

const TABS: Tab[] = ['sheet', 'setup'];

export default function ConductPage() {
  const { t } = useT();
  const { canView, can } = usePermissions();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'sheet');
  const [params] = useSearchParams();

  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);

  const mayFill = canView('conduct');
  const maySetUp = can('settings', 'update') || can('settings', 'view');

  // Every conduct endpoint is addressed by CLASS, and a class belongs to one
  // institution — so they answer 404 while a platform admin is looking at all
  // of them at once. The same honest screen the register shows.
  const { user, activeBranchId } = useAuth();
  const needsBranch = user?.branch === null && activeBranchId === null;

  const fetched = useRef(new Set<string>());

  const loadForClass = useCallback((classId: string) => {
    if (!classId || fetched.current.has(classId)) return;
    fetched.current.add(classId);
    void apiClient
      .listAll<Section>('/sections/', `?academic_class=${classId}&is_active=true`)
      .then((rows) => setSections((prev) => [
        ...prev.filter((s) => String(s.academic_class) !== classId),
        ...rows,
      ]))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!mayFill && !maySetUp) return;
    void apiClient
      .listAll<AcademicClass>('/classes/', '?is_active=true')
      .then(setClasses)
      .catch(() => setClasses([]));
    void apiClient.listAll<Stream>('/streams/', '?is_active=true').then(setStreams).catch(() => setStreams([]));
    // Gated on `settings.view`, which a teacher does not hold. An empty list is
    // the right outcome for them: the sheet endpoint picks the template itself,
    // and that is the answer they would have chosen anyway (`CLAUDE.md` §7b).
    void apiClient
      .listAll<ReportTemplate>('/report-templates/', '?ordering=name')
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, [mayFill, maySetUp]);

  if (!mayFill && !maySetUp) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Conduct')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  if (needsBranch) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Conduct')}</h1>
        <p className="mt-2 text-sm text-gray-500">
          {t('Choose an institution in the header to fill the conduct sheet.')}
        </p>
      </div>
    );
  }

  // The teacher dashboard links here with the sheet it means already chosen —
  // the one this teacher is responsible for — so they land on the grid rather
  // than on three pickers. Attendance takes the day board's link the same way.
  const initial = params.get('class')
    ? {
        academicClass: params.get('class') ?? '',
        section: params.get('section') ?? '',
        template: params.get('template') ?? '',
        date: params.get('date') ?? '',
      }
    : null;

  const tabs: TabDef<Tab>[] = [];
  if (mayFill) tabs.push({ key: 'sheet', label: t('Sheet') });
  if (maySetUp) tabs.push({ key: 'setup', label: t('Reports') });
  const active = tabs.some((x) => x.key === tab) ? tab : tabs[0].key;

  return (
    <div className="space-y-3">
      <TabStrip tabs={tabs} active={active} onChange={setTab} heading={t('Conduct')} />

      {active === 'sheet' && (
        <ConductSheetTab
          classes={classes}
          sections={sections}
          templates={templates}
          onSectionsNeeded={loadForClass}
          initial={initial}
        />
      )}
      {active === 'setup' && <ConductSetupTab classes={classes} streams={streams} />}
    </div>
  );
}
