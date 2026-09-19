import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Fee, Payment, Session } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import { formatBDTExact, formatNumber } from '../../lib/format';
import type { Period } from '../../lib/period';
import { periodLabel } from '../../lib/period';
import ExportCsvButton from '../common/ExportCsvButton';
import FilterBar, { filterSelectCls } from '../common/FilterBar';
import PeriodFilter from '../common/PeriodFilter';
import ResponsiveTable from '../common/ResponsiveTable';
import { FormError } from '../common/Field';
import Picker from '../common/Picker';
import ReportStat from './ReportStat';
import { compareMoney } from '../../lib/money';
import { todayInDhaka } from '../../lib/timezone';
import { groupBy, inPeriod, monthOf, periodRange, sumPoisha, taka } from './reportUtils';

/**
 * Fees — what came in, what has not, and who owes it (`docs/02` §4.8).
 *
 * **Reversed receipts are excluded from every collection figure and shown in
 * none of them.** A reversal is not a refund out of the day's takings; it means
 * the receipt should never have existed, and a collection sheet that counted it
 * would not reconcile with the cash box.
 *
 * Money is summed as integer poisha (`reportUtils`), never as JavaScript
 * numbers — the API sends decimal strings precisely so that no amount passes
 * through a float, and a report is not the place to give that up.
 */

type View = 'collection' | 'dues' | 'defaulters';

/** The three statuses that mean money is owed, the same set Fees ▸ Dues uses.
 *  `overdue` is not optional here: `mark_overdue` moves every past-due invoice
 *  into it overnight, so a list of unpaid+partial alone reports the dues of a
 *  system where nobody is ever late. */
const OWING: Fee['status'][] = ['unpaid', 'partial', 'overdue'];

export default function FeesReport({
  period,
  onPeriod,
  sessions,
  mayExport,
}: {
  period: Period;
  onPeriod: (p: Period) => void;
  sessions: Session[];
  mayExport: boolean;
}) {
  const { t } = useT();

  const [view, setView] = useState<View>('collection');
  const [groupMode, setGroupMode] = useState<'day' | 'month' | 'category'>('day');
  const [sessionId, setSessionId] = useState('');
  const [payments, setPayments] = useState<Payment[]>([]);
  const [fees, setFees] = useState<Fee[]>([]);
  const [loading, setLoading] = useState(true);
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
      const [paymentRows, feeRows] = await Promise.all([
        // No date filter exists on `payments`, so the period is applied below.
        apiClient.listAll<Payment>('/payments/', '?ordering=-paid_at'),
        apiClient.listAll<Fee>('/fees/', session ? `?session=${session}` : ''),
      ]);
      if (!req.isCurrent(mine)) return;
      setPayments(paymentRows);
      setFees(feeRows);
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

  const range = periodRange(period);

  const collected = useMemo(
    () => payments.filter((p) => !p.is_reversed && inPeriod(p.paid_at, range)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [payments, period],
  );

  const collectionRows = useMemo(() => {
    const key = (p: Payment) =>
      groupMode === 'category'
        ? p.category_name
        : groupMode === 'month'
          ? monthOf(p.paid_at)
          : p.paid_at.slice(0, 10);
    return [...groupBy(collected, key).entries()]
      .map(([label, rows]) => ({
        label,
        receipts: rows.length,
        amount: taka(sumPoisha(rows.map((r) => r.amount))),
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [collected, groupMode]);

  const outstanding = useMemo(
    () => fees.filter((f) => f.is_active && OWING.includes(f.status)),
    [fees],
  );

  const duesByCategory = useMemo(
    () =>
      [...groupBy(outstanding, (f) => f.category_name).entries()]
        .map(([label, rows]) => ({
          label,
          invoices: rows.length,
          payable: taka(sumPoisha(rows.map((r) => r.payable))),
          paid: taka(sumPoisha(rows.map((r) => r.paid_amount))),
          balance: taka(sumPoisha(rows.map((r) => r.balance))),
        }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [outstanding],
  );

  /** Overdue, not merely unpaid: a fee due next week is not a defaulter. */
  // Dhaka, not the browser: between midnight and 6am UTC-local machines read
  // yesterday, and a day's worth of defaulters would drop off the list.
  const today = todayInDhaka();
  const defaulters = useMemo(
    () =>
      [...groupBy(outstanding.filter((f) => f.due_date < today), (f) => f.student).entries()]
        .map(([student, rows]) => ({
          student,
          name: rows[0].student_name,
          admissionNo: rows[0].student_admission_no,
          invoices: rows.length,
          oldest: rows.map((r) => r.due_date).sort()[0],
          balance: taka(sumPoisha(rows.map((r) => r.balance))),
        }))
        .sort((a, b) => compareMoney(b.balance, a.balance)),
    [outstanding, today],
  );

  const collectedTotal = taka(sumPoisha(collected.map((p) => p.amount)));
  const dueTotal = taka(sumPoisha(outstanding.map((f) => f.balance)));

  return (
    <div className="space-y-4">
      <FilterBar
        period={<PeriodFilter value={period} onChange={onPeriod} allowAllTime />}
        active={view !== 'collection'}
      >
        <select
          value={view}
          onChange={(e) => setView(e.target.value as View)}
          aria-label={t('Report')}
          className={filterSelectCls}
        >
          <option value="collection">{t('Collection')}</option>
          <option value="dues">{t('Outstanding dues')}</option>
          <option value="defaulters">{t('Defaulter list')}</option>
        </select>
        {view === 'collection' && (
          <select
            value={groupMode}
            onChange={(e) => setGroupMode(e.target.value as 'day' | 'month' | 'category')}
            aria-label={t('Grouped by')}
            className={filterSelectCls}
          >
            <option value="day">{t('By day')}</option>
            <option value="month">{t('By month')}</option>
            <option value="category">{t('By category')}</option>
          </select>
        )}
        <Picker
          value={session}
          onChange={setSessionId}
          options={sessions.map((s) => ({ value: String(s.id), label: s.name }))}
          aria-label={t('Session')}
          className={filterSelectCls}
        />
      </FilterBar>

      <FormError message={error} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ReportStat
          label={t('Collected')}
          value={formatBDTExact(collectedTotal)}
          sub={periodLabel(period, t)}
        />
        <ReportStat label={t('Receipts')} value={formatNumber(collected.length)} />
        <ReportStat
          label={t('Outstanding')}
          value={formatBDTExact(dueTotal)}
          sub={`${formatNumber(outstanding.length)} ${t('invoices')}`}
        />
      </div>

      {view === 'collection' && (
        <>
          {mayExport && (
            <ExportCsvButton
              filename="fee-collection.csv"
              rows={() => [
                [t('Group'), t('Receipts'), t('Amount')],
                ...collectionRows.map((r) => [r.label, r.receipts, r.amount]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'label', label: t('Group'), primary: true, render: (r: (typeof collectionRows)[number]) => r.label },
              { key: 'receipts', label: t('Receipts'), render: (r: (typeof collectionRows)[number]) => formatNumber(r.receipts) },
              { key: 'amount', label: t('Amount'), render: (r: (typeof collectionRows)[number]) => formatBDTExact(r.amount) },
            ]}
            rows={collectionRows}
            rowKey={(r) => r.label}
            empty={loading ? t('Loading…') : t('Nothing was collected in this period.')}
          />
        </>
      )}

      {view === 'dues' && (
        <>
          {mayExport && (
            <ExportCsvButton
              filename="outstanding-dues.csv"
              rows={() => [
                [t('Category'), t('Invoices'), t('Payable'), t('Paid'), t('Outstanding')],
                ...duesByCategory.map((r) => [r.label, r.invoices, r.payable, r.paid, r.balance]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'label', label: t('Category'), primary: true, render: (r: (typeof duesByCategory)[number]) => r.label },
              { key: 'invoices', label: t('Invoices'), render: (r: (typeof duesByCategory)[number]) => formatNumber(r.invoices) },
              { key: 'payable', label: t('Payable'), hideOnNarrow: true, render: (r: (typeof duesByCategory)[number]) => formatBDTExact(r.payable) },
              { key: 'paid', label: t('Paid'), hideOnNarrow: true, render: (r: (typeof duesByCategory)[number]) => formatBDTExact(r.paid) },
              { key: 'balance', label: t('Outstanding'), render: (r: (typeof duesByCategory)[number]) => formatBDTExact(r.balance) },
            ]}
            rows={duesByCategory}
            rowKey={(r) => r.label}
            empty={loading ? t('Loading…') : t('Nothing is outstanding.')}
          />
        </>
      )}

      {view === 'defaulters' && (
        <>
          <p className="text-sm text-gray-500">
            {t('Invoices whose due date has passed and which are not paid in full.')}
          </p>
          {mayExport && (
            <ExportCsvButton
              filename="fee-defaulters.csv"
              rows={() => [
                [t('Student'), t('Admission no.'), t('Invoices'), t('Oldest due'), t('Outstanding')],
                ...defaulters.map((r) => [r.name, r.admissionNo, r.invoices, r.oldest, r.balance]),
              ]}
            />
          )}
          <ResponsiveTable
            columns={[
              { key: 'student', label: t('Student'), primary: true, render: (r: (typeof defaulters)[number]) => r.name },
              { key: 'admission', label: t('Admission no.'), hideOnNarrow: true, render: (r: (typeof defaulters)[number]) => r.admissionNo || '—' },
              { key: 'invoices', label: t('Invoices'), render: (r: (typeof defaulters)[number]) => formatNumber(r.invoices) },
              { key: 'oldest', label: t('Oldest due'), render: (r: (typeof defaulters)[number]) => r.oldest },
              { key: 'balance', label: t('Outstanding'), render: (r: (typeof defaulters)[number]) => formatBDTExact(r.balance) },
            ]}
            rows={defaulters}
            rowKey={(r) => r.student}
            empty={loading ? t('Loading…') : t('Nobody is overdue.')}
          />
        </>
      )}
    </div>
  );
}
