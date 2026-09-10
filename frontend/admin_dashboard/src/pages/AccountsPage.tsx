import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { Session } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { useTabParam } from '../lib/useTabParam';
import TabStrip from '../components/common/TabStrip';
import type { TabDef } from '../components/common/TabStrip';
import LedgerTab from '../components/accounts/LedgerTab';

/**
 * Accounts — the institution's ledger (`docs/02` §4.6).
 *
 * Two tabs, one component behind them: Income and Expense are the same table
 * with different endpoints.
 *
 * The line worth stating on this screen rather than in a comment: **fee
 * collections arrive here on their own.** Every receipt writes its income row in
 * the same transaction it writes the receipt, so an accountant must not type
 * those in a second time — and the Income tab shows those rows locked, with the
 * receipt number, so it is visible rather than folklore.
 */

type Tab = 'income' | 'expenses';

const TABS: Tab[] = ['income', 'expenses'];

export default function AccountsPage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const { activeBranchId } = useAuth();
  const [tab, setTab] = useTabParam<Tab>(TABS, 'income');

  const [sessions, setSessions] = useState<Session[]>([]);

  const maySee = canView('finance');

  useEffect(() => {
    if (!maySee) return;
    void apiClient.listSessions(activeBranchId).then(setSessions).catch(() => setSessions([]));
  }, [maySee, activeBranchId]);

  if (!maySee) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Accounts')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  const tabs: TabDef<Tab>[] = [
    { key: 'income', label: t('Income') },
    { key: 'expenses', label: t('Expenses') },
  ];

  return (
    <div className="space-y-3">
      <TabStrip tabs={tabs} active={tab} onChange={setTab} heading={t('Accounts')} />

      {/* `key` so switching tabs remounts rather than reusing the other
          ledger's filters, page number and rows against a different endpoint. */}
      {tab === 'income' && <LedgerTab key="income" kind="income" sessions={sessions} />}
      {tab === 'expenses' && <LedgerTab key="expense" kind="expense" sessions={sessions} />}
    </div>
  );
}
