import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { AcademicClass, FeeCategory, Session, Stream } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import CollectFeeTab from '../components/fees/CollectFeeTab';
import InvoicesTab from '../components/fees/InvoicesTab';
import DuesTab from '../components/fees/DuesTab';
import FeeSetupTab from '../components/fees/FeeSetupTab';

/**
 * Fees — `docs/02` §4.5.
 *
 * Four tabs in the order the work happens, not alphabetically. **Collect fee is
 * first and is the default**, because it is the most-used screen in the system
 * (`docs/06` #10) and an accountant opening this module wants it without a
 * second tap.
 *
 * Fee heads, streams, classes and sessions are read once here and handed down:
 * three of the four tabs need them, they change once a year, and a per-tab fetch
 * would re-read them on every tab switch.
 *
 * Permission is per tab, not per page. `fees.collect` is its own checkbox in the
 * catalogue precisely because taking money is a larger decision than seeing what
 * is owed, so somebody with `fees.view` alone gets the other three tabs and not
 * this one — rather than a Collect screen whose button 403s.
 */

type Tab = 'collect' | 'invoices' | 'dues' | 'setup';

export default function FeesPage() {
  const { t } = useT();
  const { can, canView } = usePermissions();
  const { activeBranchId } = useAuth();

  const maySee = canView('fees');
  const mayCollect = can('fees', 'collect');
  const mayUpdate = can('fees', 'update');

  const [categories, setCategories] = useState<FeeCategory[]>([]);
  const [classes, setClasses] = useState<AcademicClass[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);

  const loadCategories = useCallback(() => {
    void apiClient
      .listAll<FeeCategory>('/fee-categories/', '?ordering=display_order')
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    if (!maySee) return;
    loadCategories();
    // The three lookup lists. Each is allowed to fail on its own: an accountant
    // holds `academics.view` under the default preset but need not, and a
    // missing class list should cost a filter, not the screen.
    void apiClient.listSessions(activeBranchId).then(setSessions).catch(() => setSessions([]));
    void apiClient.listStreams(activeBranchId).then(setStreams).catch(() => setStreams([]));
    void apiClient
      .listAll<AcademicClass>('/classes/', '?is_active=true')
      .then(setClasses)
      .catch(() => setClasses([]));
  }, [maySee, activeBranchId, loadCategories]);

  // The tab list is built before `useTabParam` so an unreachable tab in a
  // pasted URL falls back to one the person can actually open.
  const tabs: TabDef<Tab>[] = [
    ...(mayCollect ? ([{ key: 'collect', label: t('Collect fee') }] as TabDef<Tab>[]) : []),
    { key: 'invoices', label: t('Invoices') },
    { key: 'dues', label: t('Dues') },
    ...(mayUpdate ? ([{ key: 'setup', label: t('Fee setup') }] as TabDef<Tab>[]) : []),
  ];
  const fallback: Tab = mayCollect ? 'collect' : 'invoices';
  const [tab, setTab] = useTabParam<Tab>(tabs.map((x) => x.key), fallback);
  const active = tabs.some((x) => x.key === tab) ? tab : fallback;

  if (!maySee) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Fees')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Fees')}</h1>
        <p className="mt-1 text-sm text-gray-500">
          {t('Take money at the counter, and see what is still owed.')}
        </p>
      </header>

      <TabStrip tabs={tabs} active={active} onChange={setTab} />

      {active === 'collect' && mayCollect && <CollectFeeTab />}
      {active === 'invoices' && (
        <InvoicesTab categories={categories} classes={classes} sessions={sessions} />
      )}
      {active === 'dues' && <DuesTab sessions={sessions} />}
      {active === 'setup' && mayUpdate && (
        <FeeSetupTab categories={categories} streams={streams} onChanged={loadCategories} />
      )}
    </div>
  );
}
