import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  AcademicClass, Enrolment, Fee, FeeCategory, Payment, Session,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { formatBDTExact, toBanglaDigits } from '../../lib/format';
import { formatDhakaDate, formatDhakaDateTime } from '../../lib/timezone';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import BaseModal from '../common/BaseModal';
import Field, { FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';
import Picker from '../common/Picker';
import FeeStatusBadge from './FeeStatusBadge';
import { FEE_STATUSES, FEE_STATUS_LABEL, methodLabel } from './feeConstants';

/** The screen's own grouping of the three states that still owe money. Not an
 *  API value — see the `status` default below for why it cannot be one. */
const OUTSTANDING = 'outstanding';
const OUTSTANDING_STATUSES: string[] = ['unpaid', 'partial', 'overdue'];

/**
 * Every invoice, and the two things that can be done to one after it exists.
 *
 * **Neither is a delete.** A waiver writes the balance off with a reason
 * attached; a reversal un-takes a receipt and reverses its income row in the
 * same transaction. Deleting a paid invoice destroys an accounting record
 * (`docs/01` §9), and both confirm dialogs say so rather than leaving the user
 * to wonder where the Delete button went.
 *
 * Two fetch strategies, for the same reason `StudentsTab` has two: **`FeeViewSet`
 * cannot filter by class or by a date range.** Its filterset is `student,
 * category, session, status, period, enrolment, generated_by, is_active`. So:
 *
 *  - **status / category / session / period / search** — real query parameters,
 *    server-paginated like everywhere else.
 *  - **class or a due-date range** — the session's enrolments decide the set and
 *    the dates are compared here, so the page is built on the client and the
 *    count still describes what is on screen.
 */

export default function InvoicesTab({
  categories,
  classes,
  sessions,
}: {
  categories: FeeCategory[];
  classes: AcademicClass[];
  sessions: Session[];
}) {
  const { t } = useT();
  const { can } = usePermissions();

  const mayWaive = can('fees', 'waive');
  const mayReverse = can('fees', 'collect');

  const [rows, setRows] = useState<Fee[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  /* **Outstanding, not this month.** An accountant opening Invoices is asking
   * "who still owes us", and that question has no date on it: a March invoice
   * left unpaid in July is exactly the row they need, and a this-month default
   * would be the one thing that hid it. So the DATE range stays empty
   * (`CLAUDE.md` §7b rule 5 is about ranges that mean "everything ever" — here
   * the status filter already bounds the list) and the STATUS filter carries
   * the default instead.
   *
   * `FeeViewSet.filterset_fields` has `status` as an exact lookup with no
   * `__in`, so the three unpaid states cannot be one query parameter. They are
   * narrowed here, on the same client-side path the class filter already
   * uses. */
  const [status, setStatus] = useState<string>(OUTSTANDING);
  const [category, setCategory] = useState('');
  const [sessionChoice, setSessionChoice] = useState('');
  const [period, setPeriod] = useState('');
  const [classFilter, setClassFilter] = useState('');
  const [dueFrom, setDueFrom] = useState('');
  const [dueTo, setDueTo] = useState('');

  const [detail, setDetail] = useState<Fee | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [reasonFor, setReasonFor] = useState<
    { kind: 'waive'; fee: Fee } | { kind: 'reverse'; payment: Payment } | null
  >(null);
  const [reason, setReason] = useState('');
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [enrolments, setEnrolments] = useState<Enrolment[]>([]);

  const sessionId = sessionChoice || String((sessions.find((s) => s.is_current) ?? sessions[0])?.id ?? '');

  // The register, for the class filter. `admissions.view` — an accountant will
  // not have it, so the class filter is hidden rather than shown empty.
  useEffect(() => {
    if (!sessionId) return;
    void apiClient
      .listAll<Enrolment>('/enrolments/', `?session=${sessionId}&is_active=true`)
      .then(setEnrolments)
      .catch(() => setEnrolments([]));
  }, [sessionId]);

  const studentsOfClass = useMemo(() => {
    if (!classFilter) return null;
    const ids = new Set<number>();
    for (const e of enrolments) if (String(e.academic_class) === classFilter) ids.add(e.student);
    return ids;
  }, [enrolments, classFilter]);

  const clientNarrowed =
    studentsOfClass !== null || dueFrom !== '' || dueTo !== '' || status === OUTSTANDING;

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);

    const q = new URLSearchParams();
    if (search.trim()) q.set('search', search.trim());
    // `OUTSTANDING` is this screen's own grouping, not an API value — it is
    // applied below, over the rows the other filters return.
    if (status && status !== OUTSTANDING) q.set('status', status);
    if (category) q.set('category', category);
    // `sessionId`, not `sessionChoice`: the derived current session is what the
    // enrolment fetch above already uses, and the list scoping itself to a
    // different session than its own class filter was simply a bug.
    if (sessionId) q.set('session', sessionId);
    if (period.trim()) q.set('period', period.trim());
    q.set('is_active', 'true');
    q.set('ordering', 'due_date');

    try {
      if (clientNarrowed) {
        const all = await apiClient.listAll<Fee>('/fees/', `?${q}`);
        const matching = all.filter(
          (f) =>
            (studentsOfClass === null || studentsOfClass.has(f.student))
            && (!dueFrom || f.due_date >= dueFrom)
            && (!dueTo || f.due_date <= dueTo)
            && (status !== OUTSTANDING || OUTSTANDING_STATUSES.includes(f.status)),
        );
        setTotal(matching.length);
        setRows(matching.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE));
      } else {
        const data = await apiClient.list<Fee>('/fees/', `?${q}&page=${page}`);
        setRows(data.results);
        setTotal(data.count);
      }
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the invoices.')));
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [search, status, category, sessionId, period, page, clientNarrowed, studentsOfClass, dueFrom, dueTo, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const openDetail = (fee: Fee) => {
    setDetail(fee);
    setPayments(null);
    setActionError(null);
    // A failure is NOT an empty list. Reported as one, a part-paid invoice
    // read "Nothing has been collected against this invoice" and the reverse
    // controls — which only exist beside a receipt — disappeared with it.
    apiClient
      .feePayments(fee.id)
      .then(setPayments)
      .catch((err) => setActionError(apiErrorText(err, t, t('Could not load the receipts for this invoice.'))));
  };

  const runAction = async () => {
    if (!reasonFor || reason.trim() === '') return;
    setActing(true);
    setActionError(null);
    try {
      if (reasonFor.kind === 'waive') {
        const updated = await apiClient.waiveFee(reasonFor.fee.id, reason.trim());
        setDetail(updated);
      } else {
        await apiClient.reversePayment(reasonFor.payment.id, reason.trim());
        if (detail) {
          // Re-read the invoice: `paid_amount` and `status` fall back out
          // server-side, and this screen must show the server's numbers.
          const fresh = await apiClient.retrieve<Fee>('/fees/', detail.id);
          setDetail(fresh);
          setPayments(await apiClient.feePayments(detail.id));
        }
      }
      setReasonFor(null);
      setReason('');
      await load();
    } catch (err) {
      setActionError(apiErrorText(err, t, t('That could not be done.')));
    } finally {
      setActing(false);
    }
  };

  const money = (v: string) => toBanglaDigits(formatBDTExact(v));

  const columns: Column<Fee>[] = [
    {
      key: 'student',
      label: t('Student'),
      primary: true,
      render: (f) => (
        // One line: the invoice number after the name, not under it.
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate font-semibold">{f.student_name}</span>
          <span className="shrink-0 font-mono text-xs font-normal text-gray-400">{f.invoice_no}</span>
        </span>
      ),
    },
    {
      key: 'category',
      label: t('Fee head'),
      render: (f) => (
        <span>
          {f.category_name}
          {f.period && <span className="text-gray-500"> · {f.period}</span>}
        </span>
      ),
    },
    { key: 'due', label: t('Due date'), render: (f) => formatDhakaDate(f.due_date), hideOnNarrow: true },
    {
      key: 'payable',
      label: t('Invoice'),
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (f) => money(f.payable),
    },
    {
      key: 'balance',
      label: t('Balance'),
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (f) => (
        <span className={f.balance === '0.00' ? 'text-gray-500' : 'font-semibold text-red-600'}>
          {money(f.balance)}
        </span>
      ),
    },
    { key: 'status', label: t('Status'), render: (f) => <FeeStatusBadge status={f.status} t={t} /> },
    {
      key: 'open',
      label: t('Open'),
      action: true,
      // Phone only: from md the row itself opens the invoice.
      cardOnly: true,
      render: (f) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            openDetail(f);
          }}
          className={btnSecondary}
        >
          {t('Open')}
        </button>
      ),
    },
  ];

  const filtersActive =
    // `OUTSTANDING` is the screen's default view, not something the user
    // switched on, so it must not light the "filters applied" marker.
    !!search || (!!status && status !== OUTSTANDING) || !!category || !!sessionChoice
    || !!period || !!classFilter || !!dueFrom || !!dueTo;

  return (
    <div className="space-y-3">
      <FilterBar
        active={filtersActive}
        onClear={() => {
          // Back to the default view, not to an unbounded one — "every invoice
          // this institution has ever raised" is not a thing anybody clears to.
          setSearch(''); setStatus(OUTSTANDING); setCategory(''); setSessionChoice('');
          setPeriod(''); setClassFilter(''); setDueFrom(''); setDueTo(''); setPage(1);
        }}
        search={
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            type="search"
            className={filterInputCls}
            placeholder={t('Invoice number, student name or id')}
            aria-label={t('Search invoices')}
          />
        }
      >
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className={filterSelectCls}
          aria-label={t('Status')}
        >
          <option value={OUTSTANDING}>{t('Outstanding')}</option>
          <option value="">{t('Every status')}</option>
          {FEE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(FEE_STATUS_LABEL[s])}
            </option>
          ))}
        </select>

        <select
          value={category}
          onChange={(e) => { setCategory(e.target.value); setPage(1); }}
          className={filterSelectCls}
          aria-label={t('Fee head')}
        >
          <option value="">{t('Every fee head')}</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name_bn || c.name}
            </option>
          ))}
        </select>

        {sessions.length > 0 && (
          <Picker
            value={sessionId}
            onChange={(v) => { setSessionChoice(v); setPage(1); }}
            options={sessions.map((s) => ({ value: String(s.id), label: s.name }))}
            className={filterSelectCls}
            aria-label={t('Session')}
          />
        )}

        {/* Hidden when the register could not be read — a class filter over an
            empty enrolment list would silently return nothing. */}
        {enrolments.length > 0 && (
          <select
            value={classFilter}
            onChange={(e) => { setClassFilter(e.target.value); setPage(1); }}
            className={filterSelectCls}
            aria-label={t('Class')}
          >
            <option value="">{t('Every class')}</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name_bn || c.name}
              </option>
            ))}
          </select>
        )}

        <input
          value={period}
          onChange={(e) => { setPeriod(e.target.value); setPage(1); }}
          type="text"
          inputMode="numeric"
          className={filterSelectCls}
          placeholder={t('Month, e.g. 2026-03')}
          aria-label={t('Fee month')}
        />

        <input
          value={dueFrom}
          onChange={(e) => { setDueFrom(e.target.value); setPage(1); }}
          type="date"
          className={filterSelectCls}
          aria-label={t('Due from')}
        />
        <input
          value={dueTo}
          onChange={(e) => { setDueTo(e.target.value); setPage(1); }}
          type="date"
          className={filterSelectCls}
          aria-label={t('Due until')}
        />
      </FilterBar>

      <FormError message={loadError} />

      {loading ? (
        <p className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('Loading…')}
        </p>
      ) : (
        <ResponsiveTable
          columns={columns}
          rows={rows}
          rowKey={(f) => f.id}
          onRowClick={openDetail}
          empty={t('No invoice matches these filters.')}
          footer={<Pagination total={total} page={page} onChange={setPage} />}
        />
      )}

      {/* ── One invoice, its receipts, and the two actions ────────────────── */}
      <BaseModal
        isOpen={detail !== null}
        onClose={() => setDetail(null)}
        title={detail ? detail.invoice_no : ''}
        maxWidth="2xl"
      >
        {detail && (
          <div className="space-y-3">
            <FormError message={actionError} />

            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-base font-bold text-gray-900">{detail.student_name}</p>
                <p className="truncate text-xs text-gray-500">
                  {[detail.category_name, detail.period, detail.student_admission_no]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
              <FeeStatusBadge status={detail.status} t={t} />
            </div>

            <dl className="divide-y divide-gray-100 rounded-xl border border-gray-100">
              {[
                [t('Amount'), money(detail.amount)],
                [t('Discount'), money(detail.discount)],
                [t('Fine'), money(detail.fine)],
                [t('Payable'), money(detail.payable)],
                [t('Paid to date'), money(detail.paid_amount)],
                [t('Balance'), money(detail.balance)],
                [t('Due date'), formatDhakaDate(detail.due_date)],
              ].map(([label, value]) => (
                <div key={label} className="flex items-start justify-between gap-3 px-3 py-2">
                  <dt className="text-xs uppercase tracking-wide text-gray-400">{label}</dt>
                  <dd className="text-right text-sm font-medium text-gray-900">{value}</dd>
                </div>
              ))}
            </dl>

            {detail.status === 'waived' && detail.waive_reason && (
              <p className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                <span className="font-semibold">{t('Waived')}: </span>
                {detail.waive_reason}
              </p>
            )}

            <section>
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
                {t('Receipts')}
              </h3>
              {payments === null && <p className="text-sm text-gray-500">{t('Loading…')}</p>}
              {payments !== null && payments.length === 0 && (
                <p className="text-sm text-gray-500">{t('Nothing has been collected against this invoice.')}</p>
              )}
              <ul className="space-y-2">
                {(payments ?? []).map((p) => (
                  <li
                    key={p.id}
                    className={`rounded-lg border p-3 ${
                      p.is_reversed ? 'border-gray-200 bg-gray-50' : 'border-gray-100 bg-white'
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p
                          className={`truncate text-sm font-semibold ${
                            p.is_reversed ? 'text-gray-500 line-through' : 'text-gray-900'
                          }`}
                        >
                          {money(p.amount)} · {p.receipt_no}
                        </p>
                        <p className="truncate text-xs text-gray-500">
                          {methodLabel(p.method, t)}
                          {p.transaction_id ? ` · ${p.transaction_id}` : ''} ·{' '}
                          {formatDhakaDateTime(p.paid_at)}
                          {p.collected_by_name ? ` · ${p.collected_by_name}` : ''}
                        </p>
                      </div>
                      {p.is_reversed ? (
                        <span className="shrink-0 rounded-full bg-gray-200 px-2.5 py-1 text-xs font-semibold text-gray-700">
                          {t('Reversed')}
                        </span>
                      ) : (
                        mayReverse && (
                          <button
                            type="button"
                            onClick={() => {
                              setReason('');
                              setReasonFor({ kind: 'reverse', payment: p });
                            }}
                            className={`${btnSecondary} shrink-0`}
                          >
                            {t('Reverse')}
                          </button>
                        )
                      )}
                    </div>
                    {p.is_reversed && p.reverse_reason && (
                      <p className="mt-1 text-xs text-gray-600">
                        {t('Reason')}: {p.reverse_reason}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>

            {mayWaive && detail.status !== 'waived' && detail.balance !== '0.00' && (
              <button
                type="button"
                onClick={() => {
                  setReason('');
                  setReasonFor({ kind: 'waive', fee: detail });
                }}
                className={`${btnSecondary} w-full justify-center`}
              >
                {t('Waive the remaining balance')}
              </button>
            )}
          </div>
        )}
      </BaseModal>

      {/* ── The reason. Required by the API, and the point of both actions ── */}
      <BaseModal
        isOpen={reasonFor !== null}
        onClose={() => setReasonFor(null)}
        title={reasonFor?.kind === 'waive' ? t('Waive this balance') : t('Reverse this receipt')}
        footer={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setReasonFor(null)}
              className={`${btnSecondary} flex-1 justify-center`}
            >
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void runAction()}
              disabled={acting || reason.trim() === ''}
              className={`${btnPrimary} flex-1 justify-center`}
            >
              {acting ? t('Saving…') : t('Confirm')}
            </button>
          </div>
        }
      >
        <div className="space-y-3">
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
            {reasonFor?.kind === 'waive'
              ? t('Waiving writes the balance off. The invoice stays on the record, marked waived, with this reason attached.')
              : t('A receipt is never deleted — deleting one would destroy an accounting record. It is marked reversed, its income entry is reversed with it, and the balance goes back up.')}
          </p>

          {reasonFor?.kind === 'reverse' && (
            <p className="text-sm text-gray-700">
              {money(reasonFor.payment.amount)} · {reasonFor.payment.receipt_no}
            </p>
          )}

          <Field label={t('Reason')} required>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={500}
              className={inputCls}
              placeholder={t('Why is this being done? Six months from now this is the only explanation there is.')}
            />
          </Field>
        </div>
      </BaseModal>
    </div>
  );
}
