import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  Income, LedgerCategory, LedgerEntry, LedgerMethod, LedgerPath, LedgerSummary, Session,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { useRequestId } from '../../lib/useRequestId';
import { formatBDTExact, formatNumber, toBanglaDigits } from '../../lib/format';
import { formatDhakaDate, todayInDhaka } from '../../lib/timezone';
import { thisMonthRange } from '../../lib/defaults';
import FilterBar, { filterInputCls, filterSelectCls } from '../common/FilterBar';
import Pagination, { PAGE_SIZE } from '../common/Pagination';
import ResponsiveTable from '../common/ResponsiveTable';
import StatusDot from '../common/StatusDot';
import type { Column } from '../common/ResponsiveTable';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import StatCard, { StatIcon } from '../common/StatCard';
import { btnPrimary, btnSecondary, inputCls, selectCls, btnRowAction } from '../common/styles';
import { PAYMENT_METHODS } from '../fees/feeConstants';
import CategoryManager from './CategoryManager';

/**
 * The ledger — one component, two tabs, because Income and Expense differ in
 * exactly two ways and everything else about them is identical.
 *
 * ### The rule this screen exists to make visible
 *
 * **A row with `source !== 'manual'` is read-only.** It was written by
 * `fees.services.collect_fee()` inside a receipt's transaction, and the API
 * refuses a PATCH on it with a 400 naming the reason. That is what makes the
 * fee ledger and the accounts unable to disagree (`docs/02` §4.6).
 *
 * So an auto-posted row is drawn differently — tinted, badged, with the receipt
 * number instead of an Edit button — rather than given a control that fails when
 * pressed. The right correction for a wrong receipt is to reverse the receipt,
 * which reverses this row with it, and the row says so.
 *
 * ### The date filter is narrowed here, not by the API
 *
 * `LedgerEntryViewSet`'s filterset has `date` as an **exact** lookup and no
 * range. A month or a from–to therefore reads the filtered rows and narrows
 * them here, the same compromise `InvoicesTab` makes for a due-date range. The
 * running total in the card is the server's `summary/` figure over the
 * server-side filters, and the screen says which rows it covers when a date
 * range is narrowing the list further.
 */

export type LedgerKind = 'income' | 'expense';

const PATH: Record<LedgerKind, LedgerPath> = { income: '/income/', expense: '/expenses/' };
const CATEGORY_PATH: Record<LedgerKind, string> = {
  income: '/income-categories/',
  expense: '/expense-categories/',
};

export default function LedgerTab({
  kind,
  sessions,
}: {
  kind: LedgerKind;
  sessions: Session[];
}) {
  const { t } = useT();
  const { can } = usePermissions();

  // Each side is its own permission: an expense clerk records expenses and
  // cannot touch income, and neither clerk corrects an entry (`update`).
  const resource = kind === 'income' ? 'income' : 'expenses';
  const mayCreate = can(resource, 'create');
  const mayUpdate = can(resource, 'update');

  const path = PATH[kind];

  const [rows, setRows] = useState<LedgerEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [summary, setSummary] = useState<LedgerSummary | null>(null);
  const [categories, setCategories] = useState<LedgerCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  /* This month, not an empty pair (`CLAUDE.md` §7b rule 5). An empty range
   * means every entry the institution has ever posted, which nobody opening a
   * ledger wants to read first — and the running total above the table is only
   * meaningful over a period somebody named. Clearing the filters still empties
   * both boxes, so "everything" stays one tap away. */
  const monthRange = thisMonthRange();
  const [from, setFrom] = useState(monthRange.from);
  const [to, setTo] = useState(monthRange.to);

  const [editing, setEditing] = useState<LedgerEntry | null | undefined>(undefined);
  const [managingCategories, setManagingCategories] = useState(false);

  const loadCategories = useCallback(() => {
    void apiClient
      .listAll<LedgerCategory>(CATEGORY_PATH[kind], '?ordering=display_order')
      .then(setCategories)
      .catch(() => setCategories([]));
  }, [kind]);

  useEffect(loadCategories, [loadCategories]);

  const dateNarrowed = from !== '' || to !== '';

  /* The filter can change while the request is in the air, and the slower of
   * two answers wins by landing last — under the new heading. */
  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    setLoading(true);
    setLoadError(null);

    const q = new URLSearchParams();
    if (search.trim()) q.set('search', search.trim());
    if (category) q.set('category', category);
    q.set('is_active', 'true');
    q.set('ordering', '-date');

    try {
      const [summaryData] = await Promise.all([
        apiClient.ledgerSummary(path, `?${q}`),
      ]);
      if (!req.isCurrent(mine)) return;
      setSummary(summaryData);

      if (dateNarrowed) {
        const all = await apiClient.listAll<LedgerEntry>(path, `?${q}`);
        if (!req.isCurrent(mine)) return;
        const matching = all.filter((r) => (!from || r.date >= from) && (!to || r.date <= to));
        setTotal(matching.length);
        setRows(matching.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE));
      } else {
        const data = await apiClient.list<LedgerEntry>(path, `?${q}&page=${page}`);
        if (!req.isCurrent(mine)) return;
        setRows(data.results);
        setTotal(data.count);
      }
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setLoadError(apiErrorText(err, t, t('Could not load the ledger.')));
      setRows([]);
      setTotal(0);
      setSummary(null);
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [path, search, category, page, dateNarrowed, from, to, req, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  const money = (v: string) => toBanglaDigits(formatBDTExact(v));

  const isPosted = (r: LedgerEntry) => r.source !== 'manual';
  const receiptNo = (r: LedgerEntry) => (r as Income).payment_receipt_no ?? '';

  const columns: Column<LedgerEntry>[] = [
    {
      key: 'what',
      label: t('Entry'),
      primary: true,
      // max-w-0 + w-full: a <td> sizes to its content, so 'truncate' inside one
      // never fires and the description pushed the table past the card instead.
      // This makes the entry column the one that gives way.
      cellClass: 'px-3 py-2 text-left max-w-0 w-full',
      // The indigo bar and the padlock are the row-level "you cannot edit this"
      // signal. `ResponsiveTable` styles rows uniformly by design, so the mark
      // goes on the cell that identifies the row — and it is the same mark in
      // the card layout and in the table.
      render: (r) => (
        // One line: the voucher and its note follow the category rather than
        // sitting under it, which doubled the height of every row in the book.
        <span className={`flex min-w-0 items-center gap-2 ${isPosted(r) ? 'border-l-4 border-indigo-400 pl-2' : ''}`}>
          <span className={`shrink-0 font-semibold ${r.is_reversed ? 'line-through text-gray-400' : ''}`}>
            {isPosted(r) && <span aria-hidden className="mr-1 text-indigo-500">🔒</span>}
            {r.category_name}
          </span>
          <span className="truncate text-xs font-normal text-gray-400">
            {r.voucher_no}
            {r.description ? ` · ${r.description}` : ''}
          </span>
        </span>
      ),
    },
    // nowrap: squeezed by the wide entry column, '10 Sept 2026' wrapped onto
    // three lines and took the whole row with it.
    {
      key: 'date',
      label: t('Date'),
      cellClass: 'px-3 py-2 text-left whitespace-nowrap',
      render: (r) => formatDhakaDate(r.date),
    },
    {
      key: 'method',
      label: t('Method'),
      hideOnNarrow: true,
      cellClass: 'px-3 py-2 text-left whitespace-nowrap',
      render: (r) => t(PAYMENT_METHODS.find((m) => m.value === r.method)?.label ?? r.method),
    },
    {
      key: 'source',
      label: t('Source'),
      render: (r) =>
        isPosted(r) ? (
          // Side by side rather than stacked: two lines here made the row two
          // lines tall for every entry in the book, posted or not.
          <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
            <StatusDot
              tone="blue"
              label={r.source === 'fee_payment' ? t('From a receipt') : t('From payroll')}
            />
            {receiptNo(r) && <span className="text-[11px] text-gray-400">{receiptNo(r)}</span>}
          </span>
        ) : (
          <StatusDot tone="gray" label={t('Entered by hand')} />
        ),
    },
    {
      key: 'amount',
      label: t('Amount'),
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (r) => (
        <span className={r.is_reversed ? 'text-gray-400 line-through' : 'font-semibold text-gray-900'}>
          {money(r.amount)}
        </span>
      ),
    },
    {
      key: 'act',
      label: t('Edit'),
      action: true,
      render: (r) =>
        isPosted(r) ? (
          // No Edit button at all. An accountant who presses one and meets a
          // 400 learns the rule the worst possible way.
          //
          // The sentence is a `title`, not a line of text: wrapped inside a
          // narrow action column it was six lines tall and made every posted
          // row six lines tall with it. The padlock on the entry cell already
          // says the row is locked; this says why, on hover.
          <span
            className="text-xs text-gray-400"
            title={
              r.source === 'fee_payment'
                ? t('Correct this by reversing the receipt in Fees.')
                : t('Posted automatically — not editable here.')
            }
          >
            {t('Locked')}
          </span>
        ) : mayUpdate ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setEditing(r);
            }}
            className={btnRowAction}
          >
            {t('Edit')}
          </button>
        ) : null,
    },
  ];

  const filtersActive = !!search || !!category || !!from || !!to;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatCard
          tone={kind === 'income' ? 'green' : 'red'}
          icon={
            <StatIcon
              d={
                kind === 'income'
                  ? 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1'
                  : 'M19 14l-7 7m0 0l-7-7m7 7V3'
              }
            />
          }
          label={kind === 'income' ? t('Total income') : t('Total expenses')}
          value={loading ? '—' : money(summary?.total ?? '0.00')}
          sub={t('Server total over the category and search filters. Reversed entries excluded.')}
          valueCls={kind === 'income' ? 'text-emerald-600' : 'text-red-600'}
        />
        <StatCard
          tone="gray"
          icon={<StatIcon d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />}
          label={t('Entries listed')}
          value={loading ? '—' : toBanglaDigits(formatNumber(total))}
          sub={dateNarrowed ? t('Narrowed by date on this screen — the total above covers every date.') : undefined}
        />
      </div>

      <FilterBar
        actions={
          <>
            {mayCreate && (
              <button type="button" onClick={() => setEditing(null)} className={btnPrimary}>
                {kind === 'income' ? t('Add income') : t('Add expense')}
              </button>
            )}
            {mayUpdate && (
              <button type="button" onClick={() => setManagingCategories(true)} className={btnSecondary}>
                {t('Manage categories')}
              </button>
            )}
          </>
        }
        active={filtersActive}
        onClear={() => {
          setSearch(''); setCategory(''); setFrom(''); setTo(''); setPage(1);
        }}
        search={
          <input
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            type="search"
            className={filterInputCls}
            placeholder={t('Voucher number, reference or description')}
            aria-label={t('Search the ledger')}
          />
        }
      >
        <select
          value={category}
          onChange={(e) => { setCategory(e.target.value); setPage(1); }}
          className={filterSelectCls}
          aria-label={t('Category')}
        >
          <option value="">{t('Every category')}</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name_bn || c.name}
            </option>
          ))}
        </select>
        <input
          value={from}
          onChange={(e) => { setFrom(e.target.value); setPage(1); }}
          type="date"
          className={filterSelectCls}
          aria-label={t('From')}
        />
        <input
          value={to}
          onChange={(e) => { setTo(e.target.value); setPage(1); }}
          type="date"
          className={filterSelectCls}
          aria-label={t('Until')}
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
          rowKey={(r) => r.id}
          empty={t('Nothing recorded here yet.')}
          footer={<Pagination total={total} page={page} onChange={setPage} />}
        />
      )}

      {editing !== undefined && (
        <LedgerEntryModal
          kind={kind}
          entry={editing}
          categories={categories}
          sessions={sessions}
          onClose={() => setEditing(undefined)}
          onSaved={() => {
            setEditing(undefined);
            void load();
          }}
        />
      )}

      {managingCategories && (
        <CategoryManager
          path={CATEGORY_PATH[kind]}
          title={kind === 'income' ? t('Income categories') : t('Expense categories')}
          rows={categories}
          onClose={() => setManagingCategories(false)}
          onChanged={loadCategories}
        />
      )}
    </div>
  );
}

/**
 * Create or edit one manual entry.
 *
 * The attachment is a **second request after the row exists** — a file cannot
 * travel in the JSON body, and there is no URL to PATCH until the row has an id.
 * A failed upload therefore leaves a saved row with no attachment, which is said
 * plainly rather than rolled back: losing a correctly entered voucher because a
 * scan failed to upload would be the worse outcome.
 */
function LedgerEntryModal({
  kind,
  entry,
  categories,
  sessions,
  onClose,
  onSaved,
}: {
  kind: LedgerKind;
  entry: LedgerEntry | null;
  categories: LedgerCategory[];
  sessions: Session[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useT();

  const [category, setCategory] = useState(String(entry?.category ?? ''));
  const [amount, setAmount] = useState(entry?.amount ?? '');
  const [date, setDate] = useState(entry?.date ?? todayInDhaka());
  const [method, setMethod] = useState<LedgerMethod>(entry?.method ?? 'cash');
  const [reference, setReference] = useState(entry?.reference ?? '');
  const [description, setDescription] = useState(entry?.description ?? '');
  const [session, setSession] = useState(String(entry?.session ?? ''));
  const [file, setFile] = useState<File | null>(null);

  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const activeCategories = useMemo(
    () => categories.filter((c) => c.is_active || String(c.id) === category),
    [categories, category],
  );

  const save = async () => {
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      category: category ? Number(category) : null,
      // The string as typed. Parsing it into a number here is the one way a
      // float could reach the books from this screen.
      amount: amount.trim(),
      date,
      method,
      reference: reference.trim(),
      description: description.trim(),
      session: session ? Number(session) : null,
    };

    try {
      const saved = entry
        ? await apiClient.patch<LedgerEntry>(PATH[kind], entry.id, body)
        : await apiClient.create<LedgerEntry>(PATH[kind], body);

      if (file) {
        try {
          await apiClient.uploadLedgerAttachment<LedgerEntry>(PATH[kind], saved.id, file);
        } catch (err) {
          // The row exists. Remembering it turns the next Save into a PATCH of
          // that row rather than a second POST — without this, a scan that
          // failed to upload left the modal open with Save enabled and
          // `entry` still null, and pressing it again booked the expense twice.
          setEntry(saved);
          setFile(null);
          setFormError(
            `${t('The entry was saved, but the attachment did not upload.')} ${apiErrorText(err, t, '')}`.trim(),
          );
          setSaving(false);
          return;
        }
      }
      onSaved();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('The entry could not be saved.')));
    } finally {
      setSaving(false);
    }
  };

  const title = entry
    ? t('Edit entry')
    : kind === 'income'
      ? t('Add income')
      : t('Add expense');

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title={title}
      maxWidth="lg"
      footer={
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className={`${btnSecondary} flex-1 justify-center`}>
            {t('Cancel')}
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving || !category || amount.trim() === ''}
            className={`${btnPrimary} flex-1 justify-center`}
          >
            {saving ? t('Saving…') : t('Save')}
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        <FormError message={formError} />

        <FieldGrid>
          <Field label={t('Category')} required error={fieldErrors.category}>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className={selectCls}
            >
              <option value="">{t('Choose one')}</option>
              {activeCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name_bn || c.name}
                </option>
              ))}
            </select>
          </Field>

          <Field label={t('Amount')} required error={fieldErrors.amount}>
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              type="text"
              inputMode="decimal"
              className={inputCls}
              placeholder="0.00"
            />
          </Field>

          <Field label={t('Date')} required error={fieldErrors.date}>
            <input
              value={date}
              onChange={(e) => setDate(e.target.value)}
              type="date"
              className={inputCls}
            />
          </Field>

          <Field label={t('Method')} error={fieldErrors.method}>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value as LedgerMethod)}
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
            label={t('Reference')}
            error={fieldErrors.reference}
            hint={t('Cheque number, bill number, transaction id.')}
          >
            <input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              type="text"
              className={inputCls}
            />
          </Field>

          {sessions.length > 0 && (
            <Field label={t('Session')} error={fieldErrors.session}>
              <select
                value={session}
                onChange={(e) => setSession(e.target.value)}
                className={selectCls}
              >
                <option value="">{t('None')}</option>
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </Field>
          )}

          <FieldWide>
            <Field label={t('Description')} error={fieldErrors.description}>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className={inputCls}
              />
            </Field>
          </FieldWide>

          <FieldWide>
            <Field
              label={t('Attachment')}
              error={fieldErrors.attachment}
              hint={t('A scan or a photo of the voucher. Uploaded after the entry is saved.')}
            >
              <input
                type="file"
                accept="image/*,application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-gray-600 file:mr-3 file:min-h-[32px] file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:text-[13px] file:font-medium file:text-gray-700"
              />
            </Field>
            {entry?.attachment && !file && (
              <p className="mt-1 text-xs text-gray-500">{t('An attachment is already on this entry.')}</p>
            )}
          </FieldWide>
        </FieldGrid>
      </div>
    </BaseModal>
  );
}
