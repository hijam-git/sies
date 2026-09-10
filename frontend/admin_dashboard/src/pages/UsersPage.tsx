import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { PermissionCatalog } from '../lib/api';
import { usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import AccountsTab from '../components/users/AccountsTab';
import RolesTab from '../components/users/RolesTab';
import ActivityTab from '../components/users/ActivityTab';

/**
 * Users — accounts, roles, and the live activity feed.
 *
 * Three tabs on one page because the sidebar carries no sub-items. The panels
 * are separate components under `components/users/`: each is a real screen with
 * its own state, and folding three of them into one file would make the
 * permission matrix impossible to find.
 *
 * The activity tab is gated on `activity.view`, not `users.view`: it is the
 * platform's audit trail over its customers, and `docs/02` §2.2 grants it to
 * nobody but the operator by default — which is exactly why it is its own
 * resource rather than part of `users`.
 */

type Tab = 'accounts' | 'roles' | 'activity';

const TABS: Tab[] = ['accounts', 'roles', 'activity'];

export default function UsersPage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'accounts');

  /**
   * Fetched once for the page and handed to both tabs that draw checkboxes.
   * Two components fetching the same catalogue would be two requests for a list
   * that changes when the backend is redeployed and not before.
   */
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  useEffect(() => {
    void apiClient
      .getPermissionCatalog()
      .then(setCatalog)
      .catch(() => setCatalogError('failed'));
  }, []);

  const maySeeUsers = canView('users');
  const maySeeActivity = canView('activity');

  if (!maySeeUsers && !maySeeActivity) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Users')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    ...(maySeeUsers
      ? ([
          { key: 'accounts', label: t('Accounts') },
          { key: 'roles', label: t('Roles') },
        ] as TabDef<Tab>[])
      : []),
    ...(maySeeActivity ? ([{ key: 'activity', label: t('Live activity') }] as TabDef<Tab>[]) : []),
  ];

  // Somebody with `activity.view` alone lands on the only tab they have, rather
  // than on an empty Accounts panel.
  const active = tabs.some((x) => x.key === tab) ? tab : tabs[0].key;

  return (
    <div className="space-y-3">
      <TabStrip tabs={tabs} active={active} onChange={setTab} heading={t('Users')} />

      {catalogError && active !== 'activity' && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {t('The permission catalogue could not be loaded, so the checkboxes are unavailable.')}
        </div>
      )}

      {active === 'accounts' && maySeeUsers && <AccountsTab catalog={catalog} />}
      {active === 'roles' && maySeeUsers && <RolesTab catalog={catalog} />}
      {active === 'activity' && maySeeActivity && <ActivityTab />}
    </div>
  );
}
