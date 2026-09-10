import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Enrolment, Fee, FeeSummaryRow, Session } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { formatBDTExact, formatNumber, toBanglaDigits } from '../../lib/format';
import { compareMoney, sumMoney } from '../../lib/money';
import { todayInDhaka } from '../../lib/timezone';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import StatCard, { StatIcon } from '../common/StatCard';
import { FormError } from '../common/Field';
import { filterSelectCls } from '../common/FilterBar';
import { btnSecondary } from '../common/styles';

/**
 * Dues — what a principal opens this module to look at.
 *
 * One question in three shapes: **how much is owed, by whom, and how long has
 * it been owed.** Everything on the screen serves that and nothing else; the
 * invoice-by-invoice view is the Invoices tab's job.
 *
 * ### Where each figure comes from, because it matters here
 *
 * The headline row is **`GET /api/fees/summary/`** — the server's own totals per
 * status, computed in the database. Those are the authority.
 *
 * The groupings below it are not something the API offers: there is no endpoint
 * that totals dues by student, by class or by age. So the outstanding invoices
 * are read (three status-filtered requests, because `status` is an exact filter)
 * and grouped here, with the addition done in **integer poisha** by
 * `lib/money.ts` — never a float. The grand total printed above the table is
 * still the server's, so a reader can check the two against each other; if they
 * ever disagree, the server is right and the list is truncated.
 */

/** The three statuses that mean money is owed. `paid` and `waived` are settled. */
const OWING = ['overdue', 'partial', 'unpaid'] as const;

/** Aged by how far past the due date, in days. The bands a Bangladeshi
 *  institution chases on: this month, last month, the term, older than that. */
const AGE_BANDS = [
  { key: 'current', label: 'Not yet due', from: -Infinity, to: -1 },
  { key: 'd0', label: '0–30 days', from: 0, to: 30 },
  { key: 'd31', label: '31–60 days', from: 31, to: 60 },
  { key: 'd61', label: '61–90 days', from: 61, to: 90 },
  { key: 'd90', label: 'Over 90 days', from: 91, to: Infinity },
] as const;

type Grouping = 'student' | 'class';

interface DuesRow {
  key: string;
  name: string;
  detail: string;
  invoices: number;
  balance: string;
  /** Days past due on the OLDEST unpaid invoice in the group — the number that
   *  says how bad it is, which an average would hide. */
  oldestDays: number;
}

/** Whole days between two `YYYY-MM-DD` dates. Date arithmetic, not money. */
function daysPast(dueDate: string, today: string): number {
  const a = Date.UTC(...(dueDate.split('-').map(Number) as [number, number, number]));
  const b = Date.UTC(...(today.split('-').map(Number) as [number, number, number]));
  // Months are 0-based in Date.UTC; both sides are off by the same month so the
  // difference is right.
  return Math.round((b - a) / 86_400_000);
}

export default function DuesTab({ sessions }: { sessions: Session[] }) {
  const { t } = useT();

  const [sessionChoice, setSessionChoice] = useState('');
  const [grouping, setGrouping] = useState<Grouping>('student');
  const [summary, setSummary] = useState<FeeSummaryRow[] | null>(null);
  const [owing, setOwing] = useState<Fee[]>([]);
  const [enrolments, setEnrolments] = useState<Enrolment[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);

  const today = todayInDhaka();
  const sessionId = sessionChoice || String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? '');

  useEffect(() => {
    if (!sessionId) return;
    void apiClient
      .listAll<Enrolment>('/enrolments/', `?session=${sessionId}&is_active=true`)
      .then(setEnrolments)
      .catch(() => setEnrolments([]));
  }, [sessionId]);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    const scope = sessionChoice ? `&session=${sessionChoice}` : '';
    try {
      const [rows, ...buckets] = await Promise.all([
        apiClient.feeSummary(`?is_active=true${scope}`),
        ...OWING.map((s) =>
          apiClient.listAll<Fee>('/fees/', `?is_active=true&status=${s}${scope}&ordering=due_date`),
        ),
      ]);
      setSummary(rows);
      const all = buckets.flat();
      setOwing(all);
      // `listAll` stops at ten pages of 200. Saying so is the difference
      // between an understated total and a lie.
      setTruncated(buckets.some((b) => b.length >= 2000));
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the dues.')));
      setSummary(null);
      setOwing([]);
    } finally {
      setLoading(false);
    }
  }, [sessionChoice, t]);

  useEffect(() => {
    // Deferred by a tick rather than called in the effect body: a setState run
    // synchronously inside an effect cascades a second render before paint.
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  // ── The server's figures ────────────────────────────────────────────────

  const owingRows = useMemo(
    () => (summary ?? []).filter((r) => (OWING as readonly string[]).includes(r.status)),
    [summary],
  );
  const totalOutstanding = useMemo(() => sumMoney(owingRows.map((r) => r.balance)), [owingRows]);
  const totalInvoices = owingRows.reduce((n, r) => n + r.count, 0);
  const overdueRow = owingRows.find((r) => r.status === 'overdue');

  // ── The groupings, built here because the API offers none ───────────────

  const classOfStudent = useMemo(() => {
    const map = new Map<number, Enrolment>();
    for (const e of enrolments) map.set(e.student, e);
    return map;
  }, [enrolments]);

  const grouped = useMemo<DuesRow[]>(() => {
    const buckets = new Map<string, { name: string; detail: string; fees: Fee[] }>();

    for (const fee of owing) {
      const enrolment = classOfStudent.get(fee.student);
      const key =
        grouping === 'student'
          ? `s${fee.student}`
          : `c${enrolment?.academic_class ?? 'none'}`;
      const name =
        grouping === 'student'
          ? fee.student_name
          : enrolment
            ? enrolment.class_name
            : t('No class recorded');
      const detail =
        grouping === 'student'
          ? [enrolment?.class_name, fee.student_admission_no].filter(Boolean).join(' · ')
          : '';

      const bucket = buckets.get(key) ?? { name, detail, fees: [] };
      bucket.fees.push(fee);
      buckets.set(key, bucket);
    }

    return [...buckets.entries()]
      .map(([key, b]) => ({
        key,
        name: b.name,
        detail: b.detail,
        invoices: b.fees.length,
        balance: sumMoney(b.fees.map((f) => f.balance)),
        oldestDays: Math.max(...b.fees.map((f) => daysPast(f.due_date, today))),
      }))
      // Biggest debt first: it is the list a principal works down.
      .sort((a, b) => compareMoney(b.balance, a.balance));
  }, [owing, grouping, classOfStudent, today, t]);

  const aged = useMemo(
    () =>
      AGE_BANDS.map((band) => {
        const fees = owing.filter((f) => {
          const d = daysPast(f.due_date, today);
          return d >= band.from && d <= band.to;
        });
        return { ...band, count: fees.length, balance: sumMoney(fees.map((f) => f.balance)) };
      }),
    [owing, today],
  );

  const money = (v: string) => toBanglaDigits(formatBDTExact(v));

  const columns: Column<DuesRow>[] = [
    {
      key: 'name',
      label: grouping === 'student' ? t('Student') : t('Class'),
      primary: true,
      render: (r) => (
        <span className="block">
          <span className="block truncate font-semibold">{r.name}</span>
          {r.detail && (
            <span className="block truncate text-xs font-normal text-gray-500">{r.detail}</span>
          )}
        </span>
      ),
    },
    {
      key: 'invoices',
      label: t('Invoices'),
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (r) => toBanglaDigits(formatNumber(r.invoices)),
    },
    {
      key: 'age',
      label: t('Oldest'),
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (r) =>
        r.oldestDays < 0 ? (
          <span className="text-gray-500">{t('Not yet due')}</span>
        ) : (
          <span className={r.oldestDays > 60 ? 'font-semibold text-red-600' : 'text-gray-700'}>
            {toBanglaDigits(formatNumber(r.oldestDays))} {t('days')}
          </span>
        ),
    },
    {
      key: 'balance',
      label: t('Outstanding'),
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (r) => <span className="font-bold text-red-600">{money(r.balance)}</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {sessions.length > 0 && (
          <select
            value={sessionChoice}
            onChange={(e) => setSessionChoice(e.target.value)}
            className={filterSelectCls}
            aria-label={t('Session')}
          >
            <option value="">{t('Every session')}</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        )}
        <div className="inline-flex overflow-hidden rounded-lg border border-gray-200">
          {(['student', 'class'] as Grouping[]).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGrouping(g)}
              aria-pressed={grouping === g}
              className={`min-h-[36px] px-3 text-[13px] font-medium transition-colors sm:min-h-[32px] ${
                grouping === g ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {g === 'student' ? t('By student') : t('By class')}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => void load()} className={`${btnSecondary} ml-auto`}>
          {t('Refresh')}
        </button>
      </div>

      <FormError message={loadError} />

      {/* The server's own totals. Everything below is grouped from the rows. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          tone="red"
          icon={<StatIcon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />}
          label={t('Total outstanding')}
          value={loading ? '—' : money(totalOutstanding)}
          sub={t('Across every unpaid, part-paid and overdue invoice')}
          valueCls="text-red-600"
        />
        <StatCard
          tone="amber"
          icon={<StatIcon d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />}
          label={t('Invoices owing')}
          value={loading ? '—' : toBanglaDigits(formatNumber(totalInvoices))}
          sub={t('Counted by the server, not by this screen')}
        />
        <StatCard
          tone="red"
          icon={<StatIcon d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />}
          label={t('Past the due date')}
          value={loading ? '—' : money(overdueRow?.balance ?? '0.00')}
          sub={
            overdueRow
              ? `${toBanglaDigits(formatNumber(overdueRow.count))} ${t('invoices')}`
              : t('Nothing overdue')
          }
          valueCls="text-red-600"
        />
      </div>

      {truncated && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t('There are more outstanding invoices than this screen reads at once. The totals in the cards above are the server’s and remain correct; narrow by session to see every row.')}
        </p>
      )}

      {/* Aged bands. Grouped here — no endpoint totals dues by age. */}
      <section className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm sm:p-5">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          {t('How long it has been owed')}
        </h3>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3 xl:grid-cols-5">
          {aged.map((band) => (
            <div key={band.key} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
              <p className="text-[11px] uppercase tracking-wide text-gray-500">{t(band.label)}</p>
              <p
                className={`mt-1 truncate text-lg font-bold ${
                  band.key === 'd90' || band.key === 'd61' ? 'text-red-600' : 'text-gray-900'
                }`}
              >
                {loading ? '—' : money(band.balance)}
              </p>
              <p className="text-[11px] text-gray-400">
                {toBanglaDigits(formatNumber(band.count))} {t('invoices')}
              </p>
            </div>
          ))}
        </div>
      </section>

      {loading ? (
        <p className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Loading…')}
        </p>
      ) : (
        <ResponsiveTable
          columns={columns}
          rows={grouped}
          rowKey={(r) => r.key}
          empty={t('Nothing is outstanding.')}
        />
      )}
    </div>
  );
}
