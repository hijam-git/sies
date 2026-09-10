import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { CollectResult, Enrolment, Fee, PaymentMethod, Student } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { formatBDTExact, toBanglaDigits } from '../../lib/format';
import { compareMoney, isPositiveMoney, subtractMoney } from '../../lib/money';
import { formatDhakaDate, todayInDhaka } from '../../lib/timezone';
import { printReceipt } from '../../lib/printReceipt';
import Field, { FormError } from '../common/Field';
import { inputCls, selectCls, btnPrimary, btnSecondary } from '../common/styles';
import BaseModal from '../common/BaseModal';
import FeeStatusBadge from './FeeStatusBadge';
import { METHODS_NEEDING_TXN, PAYMENT_METHODS, methodLabel, useLetterhead } from './feeConstants';

/**
 * Collect fee — the most-used screen in the system (`docs/06` #10).
 *
 * Designed phone-first and one-handed, because that is the real posture: an
 * accountant standing at a counter with a guardian in front of them, a phone in
 * one hand and cash in the other. Everything follows from that:
 *
 *  - **One column, one decision at a time.** Search → pick the student → pick
 *    the invoice → enter the amount → confirm. Never two of those on screen
 *    competing for a thumb.
 *  - **The confirm button is a fixed bar at the bottom** on a phone, inside the
 *    safe area, so it is reachable without shifting grip. On a laptop it sits
 *    in the flow where a mouse expects it.
 *  - **Part payment is the normal case**, not an edge case. The balance that
 *    will remain is shown before Confirm, in figures the size of the amount
 *    itself, because "did that clear it?" is the question the guardian asks
 *    next and the clerk should not have to work it out.
 *  - **The income posting is stated on the screen.** The receipt writes its own
 *    `finance.Income` row inside the same transaction (`docs/02` §4.6), and an
 *    accountant who does not know that will helpfully type it into Accounts a
 *    second time.
 *
 * Search covers name, phone and admission number. The first two are the student
 * record's own `?search=`; the third lives on **Enrolment**, whose viewset costs
 * `admissions.view` — which the accountant preset does not hold. That lookup is
 * therefore attempted and allowed to fail, and the hint under the box says which
 * three things it matches rather than promising something a 403 will withhold.
 */

/** These two are settled: nothing is owed, so they never belong on this screen. */
const SETTLED = new Set(['paid', 'waived']);

export default function CollectFeeTab() {
  const { t } = useT();
  const { can } = usePermissions();
  const letterhead = useLetterhead();

  const mayCollect = can('fees', 'collect');

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Student[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  const [student, setStudent] = useState<Student | null>(null);
  const [enrolment, setEnrolment] = useState<Enrolment | null>(null);
  const [invoices, setInvoices] = useState<Fee[]>([]);
  const [loadingInvoices, setLoadingInvoices] = useState(false);
  const [selectedFeeId, setSelectedFeeId] = useState<number | null>(null);

  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState<PaymentMethod>('cash');
  const [txnId, setTxnId] = useState('');
  const [paidOn, setPaidOn] = useState(todayInDhaka());
  const [note, setNote] = useState('');

  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [receipt, setReceipt] = useState<CollectResult | null>(null);
  const [printProblem, setPrintProblem] = useState<string | null>(null);

  const searchRef = useRef<HTMLInputElement>(null);

  // ── Search ──────────────────────────────────────────────────────────────

  const runSearch = useCallback(async (raw: string) => {
    const q = raw.trim();
    if (q.length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }
    setSearching(true);
    try {
      // Both lookups at once. The enrolment one is what makes an admission
      // number work, and its failure is expected for an accountant — the whole
      // search must not fail with it.
      const [byStudent, byEnrolment] = await Promise.all([
        apiClient
          .list<Student>('/students/', `?search=${encodeURIComponent(q)}&is_active=true&page_size=25`)
          .then((p) => p.results)
          .catch(() => [] as Student[]),
        apiClient
          .list<Enrolment>('/enrolments/', `?search=${encodeURIComponent(q)}&is_active=true&page_size=25`)
          .then((p) => p.results)
          .catch(() => [] as Enrolment[]),
      ]);

      const seen = new Set(byStudent.map((s) => s.id));
      const extraIds = byEnrolment.map((e) => e.student).filter((id) => !seen.has(id));
      const extras = await Promise.all(
        // At most a handful: an admission number matches one student, and a
        // partial one a class's worth at the very outside.
        extraIds.slice(0, 10).map((id) => apiClient.retrieve<Student>('/students/', id).catch(() => null)),
      );

      setResults([...byStudent, ...extras.filter((s): s is Student => s !== null)]);
      setSearched(true);
    } finally {
      setSearching(false);
    }
  }, []);

  useEffect(() => {
    // Debounced: a counter clerk types an eleven-digit phone number, and one
    // request per keystroke is eleven requests for one answer.
    const timer = setTimeout(() => void runSearch(query), 300);
    return () => clearTimeout(timer);
  }, [query, runSearch]);

  // ── The chosen student's outstanding invoices ───────────────────────────

  const loadInvoices = useCallback(async (chosen: Student) => {
    setLoadingInvoices(true);
    try {
      // `status` is an exact filter on this viewset, so "unpaid, partial or
      // overdue" cannot be one query. Everything active for the student comes
      // back oldest-due first and the settled two are dropped here — one
      // request rather than three, and the settled ones are needed anyway for
      // the "nothing outstanding" message to be true.
      const rows = await apiClient.listAll<Fee>(
        '/fees/',
        `?student=${chosen.id}&is_active=true&ordering=due_date`,
      );
      setInvoices(rows.filter((f) => !SETTLED.has(f.status)));
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not load this student’s invoices.')));
      setInvoices([]);
    } finally {
      setLoadingInvoices(false);
    }
  }, [t]);

  const chooseStudent = useCallback(async (chosen: Student) => {
    setStudent(chosen);
    setResults([]);
    setSearched(false);
    setQuery('');
    setSelectedFeeId(null);
    setFormError(null);
    setFieldErrors({});
    void loadInvoices(chosen);
    // Their class, for the receipt. Costs `admissions.view`; without it the
    // receipt simply prints no class line.
    apiClient
      .list<Enrolment>('/enrolments/', `?student=${chosen.id}&is_active=true&page_size=1&ordering=-enrolled_on`)
      .then((p) => setEnrolment(p.results[0] ?? null))
      .catch(() => setEnrolment(null));
  }, [loadInvoices]);

  const clearStudent = () => {
    setStudent(null);
    setEnrolment(null);
    setInvoices([]);
    setSelectedFeeId(null);
    setAmount('');
    setTxnId('');
    setNote('');
    setFormError(null);
    setFieldErrors({});
    searchRef.current?.focus();
  };

  const selectedFee = useMemo(
    () => invoices.find((f) => f.id === selectedFeeId) ?? null,
    [invoices, selectedFeeId],
  );

  const selectInvoice = (fee: Fee) => {
    setSelectedFeeId(fee.id);
    // Pre-filled with the full balance, which is what most collections are.
    // Typing over it is one tap; typing it in from scratch every time is not.
    setAmount(fee.balance);
    setFieldErrors({});
    setFormError(null);
  };

  // ── What the clerk needs to see before confirming ───────────────────────

  const overpaying = selectedFee !== null && amount.trim() !== ''
    && compareMoney(amount, selectedFee.balance) > 0;
  const amountValid = amount.trim() !== '' && isPositiveMoney(amount) && !overpaying;
  const needsTxn = METHODS_NEEDING_TXN.includes(method);
  const txnMissing = needsTxn && txnId.trim() === '';
  const remaining = selectedFee && amountValid ? subtractMoney(selectedFee.balance, amount) : null;
  const clearsInvoice = remaining !== null && !isPositiveMoney(remaining);
  const canSubmit = mayCollect && selectedFee !== null && amountValid && !txnMissing && !saving;

  const submit = async () => {
    if (!selectedFee || !canSubmit) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    try {
      const result = await apiClient.collectFee(selectedFee.id, {
        // The decimal STRING the input holds, never a parsed number — that is
        // the one place a float could get into the books from this screen.
        amount: amount.trim(),
        method,
        transaction_id: txnId.trim(),
        // A date without a time, sent as noon Dhaka: a counter records the day,
        // and midnight would land the collection on the previous day for
        // anybody reading it in UTC.
        paid_at: paidOn === todayInDhaka() ? undefined : `${paidOn}T12:00:00+06:00`,
        note: note.trim(),
      });
      setReceipt(result);
      setPrintProblem(null);
      // The list is rebuilt from the server rather than patched here, so the
      // balances on screen are the server's numbers and not this screen's
      // opinion of them.
      if (student) await loadInvoices(student);
      setSelectedFeeId(null);
      setAmount('');
      setTxnId('');
      setNote('');
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('The payment was not taken. Nothing has changed.')));
    } finally {
      setSaving(false);
    }
  };

  const doPrint = (paper: 'a4' | 'thermal') => {
    if (!receipt) return;
    const { payment, fee } = receipt;
    const ok = printReceipt(
      {
        ...letterhead,
        receiptNo: payment.receipt_no,
        paidAt: payment.paid_at,
        studentName: fee.student_name,
        studentNameBn: student?.name_bn,
        studentId: student?.student_id,
        admissionNo: fee.student_admission_no,
        className: enrolment?.class_name,
        invoiceNo: fee.invoice_no,
        categoryName: fee.category_name,
        period: fee.period,
        amount: payment.amount,
        invoicePayable: fee.payable,
        invoicePaid: fee.paid_amount,
        invoiceBalance: fee.balance,
        methodLabel: methodLabel(payment.method, t),
        transactionId: payment.transaction_id,
        collectedBy: payment.collected_by_name,
        note: payment.note,
      },
      paper,
    );
    setPrintProblem(ok ? null : t('The print window was blocked. Allow pop-ups for this site and try again.'));
  };

  // ── Render ──────────────────────────────────────────────────────────────

  const money = (v: string) => toBanglaDigits(formatBDTExact(v));

  return (
    // pb-32 on phone leaves room for the fixed confirm bar; from lg the bar is
    // in the flow and the padding is not needed.
    <div className={`space-y-4 ${selectedFee ? 'pb-32 lg:pb-0' : ''}`}>
      {/* ── 1. Who is paying ─────────────────────────────────────────────── */}
      {!student && (
        <section className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm sm:p-5">
          <h2 className="text-base font-semibold text-gray-900">{t('Find the student')}</h2>
          <p className="mt-1 text-sm text-gray-500">
            {t('Search by name, mobile number or admission number.')}
          </p>
          <div className="relative mt-3">
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              // `search` gives iOS the right keyboard and a clear button; the
              // input is 16px via `inputCls` so Safari does not zoom on focus.
              type="search"
              autoComplete="off"
              className={inputCls}
              placeholder={t('Name, mobile or admission number')}
              aria-label={t('Search students')}
            />
            {searching && (
              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">
                {t('Searching…')}
              </span>
            )}
          </div>

          {results.length > 0 && (
            <ul className="mt-3 divide-y divide-gray-100 rounded-lg border border-gray-100">
              {results.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => void chooseStudent(s)}
                    className="flex min-h-[56px] w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-blue-50"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-gray-900">
                        {s.name_bn || s.name}
                      </span>
                      <span className="block truncate text-xs text-gray-500">
                        {[s.student_id, s.phone, s.stream_name].filter(Boolean).join(' · ') || s.name}
                      </span>
                    </span>
                    <span className="shrink-0 text-blue-600" aria-hidden>›</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {searched && results.length === 0 && !searching && (
            <p className="mt-3 rounded-lg bg-gray-50 px-3 py-3 text-sm text-gray-600">
              {t('No student matched that. Try part of the name, or the full mobile number.')}
            </p>
          )}
        </section>
      )}

      {/* ── 2. The student, and what they owe ────────────────────────────── */}
      {student && (
        <>
          <section className="rounded-xl border border-blue-100 bg-blue-50 p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-base font-bold text-gray-900">
                  {student.name_bn || student.name}
                </p>
                <p className="mt-0.5 truncate text-xs text-gray-600">
                  {[
                    student.student_id,
                    enrolment?.class_name,
                    enrolment?.admission_number,
                    student.phone,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
              <button type="button" onClick={clearStudent} className={`${btnSecondary} shrink-0`}>
                {t('Change')}
              </button>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              {t('Outstanding invoices')}
            </h2>

            {loadingInvoices && <p className="text-sm text-gray-500">{t('Loading…')}</p>}

            {!loadingInvoices && invoices.length === 0 && (
              <p className="rounded-xl border border-emerald-100 bg-emerald-50 p-4 text-sm font-medium text-emerald-800">
                {t('Nothing is outstanding for this student.')}
              </p>
            )}

            {invoices.map((fee) => {
              const chosen = fee.id === selectedFeeId;
              return (
                <button
                  key={fee.id}
                  type="button"
                  onClick={() => selectInvoice(fee)}
                  aria-pressed={chosen}
                  className={`block w-full rounded-xl border p-4 text-left transition-colors ${
                    chosen
                      ? 'border-blue-600 bg-blue-50 ring-2 ring-blue-200'
                      : 'border-gray-100 bg-white shadow-sm hover:border-blue-200'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-gray-900">
                        {fee.category_name}
                        {fee.period && <span className="text-gray-500"> · {fee.period}</span>}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-gray-500">
                        {fee.invoice_no} · {t('Due')} {formatDhakaDate(fee.due_date)}
                      </p>
                    </div>
                    <FeeStatusBadge status={fee.status} t={t} />
                  </div>
                  <div className="mt-3 flex items-end justify-between gap-3">
                    <span className="text-xs text-gray-500">
                      {t('Invoice')} {money(fee.payable)} · {t('Paid')} {money(fee.paid_amount)}
                    </span>
                    <span className="text-right">
                      <span className="block text-[11px] uppercase tracking-wide text-gray-400">
                        {t('Balance')}
                      </span>
                      <span className="block text-lg font-bold text-red-600">{money(fee.balance)}</span>
                    </span>
                  </div>
                </button>
              );
            })}
          </section>
        </>
      )}

      {/* ── 3. The payment ───────────────────────────────────────────────── */}
      {selectedFee && (
        <section className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm sm:p-5">
          <h2 className="text-base font-semibold text-gray-900">{t('Take the payment')}</h2>

          <FormError message={formError} />

          {!mayCollect && (
            <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {t('You may look at fees but not collect them.')}
            </p>
          )}

          <div className="mt-4 space-y-4">
            <Field
              label={t('Amount received')}
              required
              error={fieldErrors.amount}
              hint={t('Part payment is fine — enter what is being handed over.')}
            >
              <input
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                // `decimal` gives a numeric keypad WITH a decimal point; plain
                // `numeric` does not, and fifty poisha exists.
                inputMode="decimal"
                type="text"
                className={`${inputCls} text-xl font-bold`}
                placeholder="0.00"
              />
            </Field>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setAmount(selectedFee.balance)}
                className={`${btnSecondary} min-h-[44px]`}
              >
                {t('Full balance')} · {money(selectedFee.balance)}
              </button>
            </div>

            {overpaying && (
              <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
                {t('That is more than is outstanding on this fee.')}
              </p>
            )}

            {/* The single most useful thing on this screen after the amount. */}
            {remaining !== null && (
              <div
                className={`rounded-xl border p-4 ${
                  clearsInvoice ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'
                }`}
              >
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                  {t('Balance remaining after this payment')}
                </p>
                <p
                  className={`mt-1 text-2xl font-bold ${
                    clearsInvoice ? 'text-emerald-700' : 'text-amber-800'
                  }`}
                >
                  {money(remaining)}
                </p>
                <p className="mt-1 text-xs text-gray-600">
                  {clearsInvoice
                    ? t('This clears the invoice in full.')
                    : t('This is a part payment — the invoice stays open.')}
                </p>
              </div>
            )}

            <Field label={t('Method')} required error={fieldErrors.method}>
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as PaymentMethod)}
                className={selectCls}
              >
                {PAYMENT_METHODS.map((m) => (
                  <option key={m.value} value={m.value}>
                    {t(m.label)}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              label={t('Transaction id')}
              required={needsTxn}
              error={fieldErrors.transaction_id}
              hint={
                needsTxn
                  ? t('A mobile payment needs its transaction id to be reconciled later.')
                  : t('Cheque number, bank slip or card reference. Optional for cash.')
              }
            >
              <input
                value={txnId}
                onChange={(e) => setTxnId(e.target.value)}
                type="text"
                autoComplete="off"
                className={inputCls}
                placeholder={needsTxn ? t('e.g. 8N7A2K1B9C') : ''}
              />
            </Field>

            <Field label={t('Date received')} error={fieldErrors.paid_at}>
              <input
                value={paidOn}
                onChange={(e) => setPaidOn(e.target.value)}
                type="date"
                max={todayInDhaka()}
                className={inputCls}
              />
            </Field>

            <Field label={t('Note')} error={fieldErrors.note}>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                type="text"
                className={inputCls}
                placeholder={t('Optional — anything the receipt should say')}
              />
            </Field>

            {/* The one line an accountant must read on this screen. */}
            <p className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-900">
              {t('This collection posts itself to Income automatically — do not enter it again in Accounts.')}
            </p>
          </div>

          {/* Desktop: the button in the flow. Phone: the fixed bar below. */}
          <div className="mt-5 hidden lg:block">
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!canSubmit}
              className={`${btnPrimary} min-h-[48px] w-full sm:w-auto`}
            >
              {saving ? t('Taking payment…') : `${t('Confirm and print receipt')} · ${money(amount || '0')}`}
            </button>
          </div>
        </section>
      )}

      {/* Fixed thumb-reachable confirm bar, phone and tablet only. */}
      {selectedFee && (
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-gray-200 bg-white/95 px-4 py-3 pb-safe shadow-[0_-4px_16px_rgba(0,0,0,0.06)] backdrop-blur lg:hidden">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <span className="text-xs uppercase tracking-wide text-gray-500">{t('Remaining')}</span>
            <span className="text-sm font-bold text-gray-900">
              {remaining === null ? '—' : money(remaining)}
            </span>
          </div>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSubmit}
            className={`${btnPrimary} min-h-[52px] w-full text-base`}
          >
            {saving ? t('Taking payment…') : `${t('Confirm')} ${money(amount || '0')}`}
          </button>
        </div>
      )}

      {/* ── 4. The receipt ───────────────────────────────────────────────── */}
      <BaseModal
        isOpen={receipt !== null}
        onClose={() => setReceipt(null)}
        title={t('Payment received')}
        maxWidth="lg"
        footer={
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => doPrint('a4')}
              className={`${btnPrimary} min-h-[48px] flex-1 justify-center`}
            >
              {t('Print A4')}
            </button>
            <button
              type="button"
              onClick={() => doPrint('thermal')}
              className={`${btnSecondary} min-h-[48px] flex-1 justify-center`}
            >
              {t('Print on the roll (80mm)')}
            </button>
            <button
              type="button"
              onClick={() => setReceipt(null)}
              className={`${btnSecondary} min-h-[48px] flex-1 justify-center`}
            >
              {t('Done')}
            </button>
          </div>
        }
      >
        {receipt && (
          <div className="space-y-4">
            <div className="rounded-xl border-2 border-emerald-200 bg-emerald-50 p-4 text-center">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                {t('Received')}
              </p>
              <p className="mt-1 text-3xl font-bold text-emerald-800">
                {money(receipt.payment.amount)}
              </p>
              <p className="mt-1 text-sm text-emerald-900">
                {t('Receipt')} {receipt.payment.receipt_no}
              </p>
            </div>

            <dl className="divide-y divide-gray-100 rounded-xl border border-gray-100">
              {[
                [t('Student'), receipt.fee.student_name],
                [t('Invoice'), `${receipt.fee.invoice_no} · ${receipt.fee.category_name}`],
                [t('Method'), methodLabel(receipt.payment.method, t)],
                [t('Transaction id'), receipt.payment.transaction_id || '—'],
                [t('Collected by'), receipt.payment.collected_by_name || '—'],
                [t('Invoice total'), money(receipt.fee.payable)],
                [t('Paid to date'), money(receipt.fee.paid_amount)],
                [t('Balance remaining'), money(receipt.fee.balance)],
              ].map(([label, value]) => (
                <div key={label} className="flex items-start justify-between gap-3 px-3 py-2">
                  <dt className="text-xs uppercase tracking-wide text-gray-400">{label}</dt>
                  <dd className="min-w-0 text-right text-sm font-medium text-gray-900">{value}</dd>
                </div>
              ))}
            </dl>

            <p className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-sm text-blue-900">
              {t('This collection posts itself to Income automatically — do not enter it again in Accounts.')}
            </p>

            {printProblem && <FormError message={printProblem} />}
          </div>
        )}
      </BaseModal>
    </div>
  );
}
