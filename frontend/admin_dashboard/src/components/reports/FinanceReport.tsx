import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Branch, LedgerEntry, Session } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import { formatBDTExact, formatNumber, formatPercent } from '../../lib/format';
import type { Period } from '../../lib/period';
import { periodLabel } from '../../lib/period';
import ExportCsvButton from '../common/ExportCsvButton';
import FilterBar, { filterSelectCls } from '../common/FilterBar';
import PeriodFilter from '../common/PeriodFilter';
import ResponsiveTable from '../common/ResponsiveTable';
import { FormError } from '../common/Field';
import Picker from '../common/Picker';
import ReportStat from './ReportStat';
import { groupBy, inPeriod, periodRange, share, sumPoisha, taka } from './reportUtils';

/**
 * Finance — the income and expense statement, and the comparison across
 * institutions (`docs/02` §4.8).
 *
 * **The cross-institution view is the platform admin's alone**, and it is the
 * reason the branch model exists (`docs/08` D1): the operator of SIES needs one
 * page that says which institution is collecting its fees and which is not. A
 * principal never sees it — they hold `finance.view` for their own institution
 * and must not meet a league table of everybody else's.
 *
 * Reversed entries are excluded from every figure. A reversed voucher is one
 * that should not have existed; counting it would overstate the month.
 */

type View = 'statement' | 'categories' | 'institutions';

interface BranchRow {
  id: number;
  name: string;
  strength: number;
  payable: string;
  paid: string;
  collection: number | null;
  income: string;
  expense: string;
  net: string;
}

export default function FinanceReport({
  period,
  onPeriod,
  sessions,
  isPlatformAdmin,
  mayExport,
}: {
  period: Period;
  onPeriod: (p: Period) => void;
  sessions: Session[];
  isPlatformAdmin: boolean;
  mayExport: boolean;
}) {
  const { t } = useT();

  const [view, setView] = useState<View>('statement');
  const [sessionId, setSessionId] = useState('');
  const [income, setIncome] = useState<LedgerEntry[]>([]);
  const [expenses, setExpenses] = useState<LedgerEntry[]>([]);
  const [branchRows, setBranchRows] = useState<BranchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [truncated, setTruncated] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentSession = useMemo(
    () => String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? ''),
    [sessions],
  );
  const session = sessionId || currentSession;

  /* The filter can change while the request is in the air, and the slower of
   * two answers wins by landing last — under the new heading. `req` says
   * whether this answer is still the one being waited for. */
  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    setLoading(true);
    setError(null);
    try {
      const query = session ? `?session=${session}` : '';
      const [incomeRows, expenseRows] = await Promise.all([
        // `date` is an exact-match filter on these endpoints, not a range, so
        // the period is applied on the rows below.
        apiClient.listAll<LedgerEntry>('/income/', query),
        apiClient.listAll<LedgerEntry>('/expenses/', query),
      ]);
      if (!req.isCurrent(mine)) return;
      setIncome(incomeRows);
      setExpenses(expenseRows);
      // Same bound as everywhere else: ten pages of 200, and silence about
      // hitting it would understate Income, Expenses and Net together.
      setTruncated(incomeRows.length >= 2000 || expenseRows.length >= 2000);
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setError(apiErrorText(err, t, t('Could not load this report.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [session, req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  /** The comparison, one institution at a time.
   *
   *  Four requests per institution and no more: the fee summary carries the
   *  collection ratio, the two ledger summaries carry the money, and a
   *  one-row student page carries the strength in its `count`. The server does
   *  every sum. */
  const loadInstitutions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const branches = await apiClient.getBranches();
      const rows = await Promise.all(
        branches.map(async (branch: Branch): Promise<BranchRow> => {
          const scope = `?branch=${branch.id}`;
          const [fees, incomeSummary, expenseSummary, students] = await Promise.all([
            apiClient.feeSummary(scope).catch(() => []),
            apiClient.ledgerSummary('/income/', scope).catch(() => ({ total: '0', by_category: [] })),
            apiClient.ledgerSummary('/expenses/', scope).catch(() => ({ total: '0', by_category: [] })),
            apiClient.list<{ id: number }>('/students/', `${scope}&is_active=true&page_size=1`)
              .catch(() => ({ count: 0, next: null, previous: null, results: [] })),
          ]);
          const payable = sumPoisha(fees.map((f) => f.payable));
          const paid = sumPoisha(fees.map((f) => f.paid));
          const net = sumPoisha([incomeSummary.total]) - sumPoisha([expenseSummary.total]);
          return {
            id: branch.id,
            name: branch.name_bn || branch.name,
            strength: students.count,
            payable: taka(payable),
            paid: taka(paid),
            collection: share(paid, payable),
            income: taka(sumPoisha([incomeSummary.total])),
            expense: taka(sumPoisha([expenseSummary.total])),
            net: taka(net),
          };
        }),
      );
      setBranchRows(rows);
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not load this report.')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (view !== 'institutions' || !isPlatformAdmin) return;
    const timer = setTimeout(() => void loadInstitutions(), 0);
    return () => clearTimeout(timer);
  }, [view, isPlatformAdmin, loadInstitutions]);

  /** Live rows inside the period. Reversed and inactive entries are dropped
   *  here once, so no figure below can accidentally include one. */
  const live = useCallback(
    (rows: LedgerEntry[]) => {
      const range = periodRange(period);
      return rows.filter((r) => r.is_active && !r.is_reversed && inPeriod(r.date, range));
    },
    [period],
  );

  const periodIncome = useMemo(() => live(income), [income, live]);
  const periodExpenses = useMemo(() => live(expenses), [expenses, live]);

  const incomeTotal = sumPoisha(periodIncome.map((r) => r.amount));
  const expenseTotal = sumPoisha(periodExpenses.map((r) => r.amount));

  const categoryRows = useMemo(() => {
    const build = (rows: LedgerEntry[], kind: string) =>
      [...groupBy(rows, (r) => r.category_name).entries()].map(([label, group]) => ({
        key: `${kind}-${label}`,
        kind,
        label,
        count: group.length,
        amount: taka(sumPoisha(group.map((r) => r.amount))),
      }));
    return [...build(periodIncome, t('Income')), ...build(periodExpenses, t('Expense'))];
  }, [periodIncome, periodExpenses, t]);

  const statementRows = [
    { key: 'income', label: t('Income'), amount: taka(incomeTotal), count: periodIncome.length },
    { key: 'expense', label: t('Expense'), amount: taka(expenseTotal), count: periodExpenses.length },
    { key: 'net', label: t('Net'), amount: taka(incomeTotal - expenseTotal), count: 0 },
  ];

  return (
    <div className="space-y-4">
      <FilterBar
        period={<PeriodFilter value={period} onChange={onPeriod} allowAllTime />}
        active={view !== 'statement'}
      >
        <select
          value={view}
          onChange={(e) => setView(e.target.value as View)}
          aria-label={t('Report')}
          className={filterSelectCls}
        >
          <option value="statement">{t('Income and expense')}</option>
          <option value="categories">{t('Category breakdown')}</option>
          {isPlatformAdmin && <option value="institutions">{t('Compare institutions')}</option>}
        </select>
        <Picker
          value={session}
          onChange={setSessionId}
          options={sessions.map((s) => ({ value: String(s.id), label: s.name }))}
          aria-label={t('Session')}
          className={filterSelectCls}
        />
      </FilterBar>

      <FormError message={error} />

      {truncated && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t('This report reads at most 2,000 rows per list, and one of them reached that. The figures below are understated — narrow the period or the session.')}
        </p>
      )}

      {view !== 'institutions' && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <ReportStat
            label={t('Income')}
            value={formatBDTExact(taka(incomeTotal))}
            sub={periodLabel(period, t)}
          />
          <ReportStat label={t('Expense')} value={formatBDTExact(taka(expenseTotal))} />
          <ReportStat label={t('Net')} value={formatBDTExact(taka(incomeTotal - expenseTotal))} />
        </div>
      )}

      {view === 'statement' && (
        <>
          {mayExport && (
            <ExportCsvButton
              filename="income-expense.csv"
              rows={() => [
                [t('Line'), t('Entries'), t('Amount')],
                ...statementRows.map((r) => [r.label, r.count, r.amount]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'label', label: t('Line'), primary: true, render: (r: (typeof statementRows)[number]) => r.label },
              { key: 'count', label: t('Entries'), render: (r: (typeof statementRows)[number]) => (r.key === 'net' ? '—' : formatNumber(r.count)) },
              { key: 'amount', label: t('Amount'), render: (r: (typeof statementRows)[number]) => formatBDTExact(r.amount) },
            ]}
            rows={statementRows}
            rowKey={(r) => r.key}
            empty={loading ? t('Loading…') : t('Nothing was posted in this period.')}
          />
        </>
      )}

      {view === 'categories' && (
        <>
          {mayExport && (
            <ExportCsvButton
              filename="finance-categories.csv"
              rows={() => [
                [t('Kind'), t('Category'), t('Entries'), t('Amount')],
                ...categoryRows.map((r) => [r.kind, r.label, r.count, r.amount]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'label', label: t('Category'), primary: true, render: (r: (typeof categoryRows)[number]) => r.label },
              { key: 'kind', label: t('Kind'), render: (r: (typeof categoryRows)[number]) => r.kind },
              { key: 'count', label: t('Entries'), hideOnNarrow: true, render: (r: (typeof categoryRows)[number]) => formatNumber(r.count) },
              { key: 'amount', label: t('Amount'), render: (r: (typeof categoryRows)[number]) => formatBDTExact(r.amount) },
            ]}
            rows={categoryRows}
            rowKey={(r) => r.key}
            empty={loading ? t('Loading…') : t('Nothing was posted in this period.')}
          />
        </>
      )}

      {view === 'institutions' && isPlatformAdmin && (
        <>
          <p className="text-sm text-gray-500">
            {t('Every institution on the platform, side by side. Collection is paid against payable for the session; the money is all-time until the ledger gains a date range.')}
          </p>
          {mayExport && (
            <ExportCsvButton
              filename="institutions.csv"
              rows={() => [
                [t('Institution'), t('Strength'), t('Payable'), t('Paid'), t('Collection'), t('Income'), t('Expense'), t('Net')],
                ...branchRows.map((r) => [
                  r.name,
                  r.strength,
                  r.payable,
                  r.paid,
                  formatPercent(r.collection),
                  r.income,
                  r.expense,
                  r.net,
                ]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'name', label: t('Institution'), primary: true, render: (r: BranchRow) => r.name },
              { key: 'strength', label: t('Strength'), render: (r: BranchRow) => formatNumber(r.strength) },
              { key: 'collection', label: t('Collection'), render: (r: BranchRow) => formatPercent(r.collection) },
              { key: 'income', label: t('Income'), hideOnNarrow: true, render: (r: BranchRow) => formatBDTExact(r.income) },
              { key: 'expense', label: t('Expense'), hideOnNarrow: true, render: (r: BranchRow) => formatBDTExact(r.expense) },
              { key: 'net', label: t('Net'), render: (r: BranchRow) => formatBDTExact(r.net) },
            ]}
            rows={branchRows}
            rowKey={(r) => r.id}
            empty={loading ? t('Loading…') : t('No institutions to compare.')}
          />
          <p className="text-xs text-gray-500">
            {t('Attendance is not compared here: the only endpoint that reads attendance is one class’s month register, so a platform-wide figure would be one request per class per institution. It needs a summary endpoint.')}
          </p>
        </>
      )}
    </div>
  );
}
