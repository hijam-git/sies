import { useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { FeeCategory, Recurrence, Stream } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import { formatBDTExact, toBanglaDigits } from '../../lib/format';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls, btnRowAction } from '../common/styles';
import { RECURRENCES } from './feeConstants';

/**
 * The heads of charge — eleven seeded per institution, extendable.
 *
 * ### The flag, and why it is the point of this screen
 *
 * **A head with no `default_amount` cannot have an invoice raised for it by the
 * monthly job**, and nothing anywhere else says so. An institution turns on
 * Transport Fee, waits a month, and no transport invoice appears — with no
 * error, because from the job's point of view nothing was wrong. So every row
 * missing an amount is called out here, in the row and in a count at the top.
 *
 * ### The amount is editable, and the screen decides that from the payload
 *
 * `default_amount` was once on the model but missing from
 * `FeeCategorySerializer`, so a PATCH carrying it was accepted and silently
 * dropped — every head stayed unpriced and the monthly job raised nothing. The
 * serializer carries it now, and `amountServed` below reads that off the rows
 * themselves rather than off a version flag: present in the payload means the
 * input is enabled and sent, absent means it is shown read-only with the
 * reason. An API that loses the field again degrades instead of pretending.
 */

export default function FeeSetupTab({
  categories,
  streams,
  onChanged,
}: {
  categories: FeeCategory[];
  streams: Stream[];
  onChanged: () => void;
}) {
  const { t } = useT();
  const { can } = usePermissions();

  // Reading heads is `fees.view`; **editing one is `settings.update`** — a head
  // is the institution's price list, and the server gates it that way (the
  // catalogue's `settings` hint names fee categories). Gating the buttons on
  // `fees.update` offered an admission officer an editor that would 403.
  const mayUpdate = can('settings', 'update');

  const [editing, setEditing] = useState<FeeCategory | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [recurrence, setRecurrence] = useState<Recurrence>('monthly');
  const [defaultAmount, setDefaultAmount] = useState('');
  const [isMandatory, setIsMandatory] = useState(false);
  const [isRefundable, setIsRefundable] = useState(false);
  const [isActive, setIsActive] = useState(true);
  const [appliesStreams, setAppliesStreams] = useState<number[]>([]);
  const [hostelOnly, setHostelOnly] = useState(false);
  const [transportOnly, setTransportOnly] = useState(false);

  /** Whether the running API serves the field at all. Read from the data, so a
   *  serializer change needs no edit here. */
  const amountServed = useMemo(
    () => categories.some((c) => Object.prototype.hasOwnProperty.call(c, 'default_amount')),
    [categories],
  );

  const missingAmount = useMemo(
    () => categories.filter((c) => c.is_active && !c.default_amount),
    [categories],
  );

  const open = (c: FeeCategory) => {
    setEditing(c);
    setRecurrence(c.recurrence);
    setDefaultAmount(c.default_amount ?? '');
    setIsMandatory(c.is_mandatory);
    setIsRefundable(c.is_refundable);
    setIsActive(c.is_active);
    setAppliesStreams(c.applies_to?.streams ?? []);
    setHostelOnly(c.applies_to?.hostel_only ?? false);
    setTransportOnly(c.applies_to?.transport_only ?? false);
    setFormError(null);
    setFieldErrors({});
  };

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await apiClient.patch<FeeCategory>('/fee-categories/', editing.id, {
        recurrence,
        is_mandatory: isMandatory,
        is_refundable: isRefundable,
        is_active: isActive,
        applies_to: {
          streams: appliesStreams,
          hostel_only: hostelOnly,
          transport_only: transportOnly,
        },
        // Sent only when the API actually serves the field. Sending it blind
        // would look like it worked.
        ...(amountServed ? { default_amount: defaultAmount.trim() || null } : {}),
      });
      setEditing(null);
      onChanged();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('The fee head could not be saved.')));
    } finally {
      setSaving(false);
    }
  };

  const toggleStream = (id: number) =>
    setAppliesStreams((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const appliesLabel = (c: FeeCategory) => {
    const parts: string[] = [];
    if (c.applies_to?.hostel_only) parts.push(t('Residential students only'));
    if (c.applies_to?.transport_only) parts.push(t('Transport users only'));
    const ids = c.applies_to?.streams ?? [];
    if (ids.length > 0) {
      parts.push(
        ids
          .map((id) => {
            const stream = streams.find((s) => s.id === id);
            return stream ? stream.name_bn || stream.name : `#${id}`;
          })
          .join(', '),
      );
    }
    return parts.length > 0 ? parts.join(' · ') : t('Every student');
  };

  const columns: Column<FeeCategory>[] = [
    {
      key: 'name',
      label: t('Fee head'),
      primary: true,
      render: (c) => (
        <span className="block">
          <span className="block truncate font-semibold">{c.name_bn || c.name}</span>
          <span className="block truncate text-xs font-normal text-gray-500">
            {c.code}
            {c.is_system ? ` · ${t('Seeded')}` : ''}
          </span>
        </span>
      ),
    },
    {
      key: 'amount',
      label: t('Default amount'),
      cellClass: 'px-3 py-2 text-right',
      headClass: 'px-3 py-2 text-right',
      render: (c) =>
        c.default_amount ? (
          <span className="font-medium">{toBanglaDigits(formatBDTExact(c.default_amount))}</span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
            {t('No amount set')}
          </span>
        ),
    },
    {
      key: 'recurrence',
      label: t('Charged'),
      render: (c) => t(RECURRENCES.find((r) => r.value === c.recurrence)?.label ?? c.recurrence),
    },
    { key: 'applies', label: t('Applies to'), render: appliesLabel, hideOnNarrow: true },
    {
      key: 'active',
      label: t('Active'),
      render: (c) =>
        c.is_active ? (
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-800">
            {t('Active')}
          </span>
        ) : (
          <span className="rounded-full bg-gray-200 px-2.5 py-1 text-xs font-semibold text-gray-600">
            {t('Off')}
          </span>
        ),
    },
    {
      key: 'edit',
      label: t('Edit'),
      action: true,
      render: (c) =>
        mayUpdate ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              open(c);
            }}
            className={btnRowAction}
          >
            {t('Edit')}
          </button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-4">
      {/* The whole reason this screen exists. Above the table, not inside it. */}
      {missingAmount.length > 0 && (
        <div className="rounded-xl border-l-4 border-amber-400 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-900">
            {toBanglaDigits(String(missingAmount.length))}{' '}
            {t('active fee heads have no default amount.')}
          </p>
          <p className="mt-1 text-sm leading-relaxed text-amber-800">
            {t('An invoice cannot be raised for a head with no amount — the monthly job skips it silently, so nothing else on any screen would ever tell you.')}
          </p>
          <p className="mt-2 text-sm font-medium text-amber-900">
            {missingAmount.map((c) => c.name_bn || c.name).join(' · ')}
          </p>
        </div>
      )}

      {!amountServed && (
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
          <p className="text-sm font-semibold text-gray-800">
            {t('The default amount cannot be edited from here yet.')}
          </p>
          <p className="mt-1 text-sm leading-relaxed text-gray-600">
            {t('This build of the API does not send or accept the field on a fee head. Set it in Django admin until it does; this screen will edit it as soon as the field is served.')}
          </p>
        </div>
      )}

      <ResponsiveTable
        columns={columns}
        rows={categories}
        rowKey={(c) => c.id}
        onRowClick={mayUpdate ? open : undefined}
        empty={t('No fee heads yet. They are seeded when the institution is created.')}
      />

      <BaseModal
        isOpen={editing !== null}
        onClose={() => setEditing(null)}
        title={editing ? editing.name_bn || editing.name : ''}
        maxWidth="lg"
        footer={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setEditing(null)}
              className={`${btnSecondary} flex-1 justify-center`}
            >
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className={`${btnPrimary} flex-1 justify-center`}
            >
              {saving ? t('Saving…') : t('Save')}
            </button>
          </div>
        }
      >
        {editing && (
          <div className="space-y-4">
            <FormError message={formError} />

            <FieldGrid>
              <Field
                label={t('Default amount')}
                error={fieldErrors.default_amount}
                hint={
                  amountServed
                    ? t('Leave empty only if the amount differs per student every time.')
                    : t('Read-only: this build of the API does not accept the field.')
                }
              >
                <input
                  value={defaultAmount}
                  onChange={(e) => setDefaultAmount(e.target.value)}
                  type="text"
                  inputMode="decimal"
                  disabled={!amountServed}
                  className={inputCls}
                  placeholder="0.00"
                />
              </Field>

              <Field label={t('Charged')} error={fieldErrors.recurrence}>
                <select
                  value={recurrence}
                  onChange={(e) => setRecurrence(e.target.value as Recurrence)}
                  className={selectCls}
                >
                  {RECURRENCES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {t(r.label)}
                    </option>
                  ))}
                </select>
              </Field>

              <FieldWide>
                <fieldset>
                  <legend className="mb-2 text-sm font-medium text-gray-700">
                    {t('Applies to')}
                  </legend>
                  <p className="mb-2 text-xs text-gray-500">
                    {t('No stream ticked means every stream.')}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {streams.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => toggleStream(s.id)}
                        aria-pressed={appliesStreams.includes(s.id)}
                        className={`min-h-[36px] rounded-md border px-3 text-[13px] font-medium transition-colors sm:min-h-[32px] ${
                          appliesStreams.includes(s.id)
                            ? 'border-blue-600 bg-blue-50 text-blue-700'
                            : 'border-gray-200 bg-white text-gray-600'
                        }`}
                      >
                        {s.name_bn || s.name}
                      </button>
                    ))}
                  </div>
                </fieldset>
              </FieldWide>

              <FieldWide>
                <div className="space-y-2">
                  {[
                    { on: hostelOnly, set: setHostelOnly, label: t('Only residential students') },
                    { on: transportOnly, set: setTransportOnly, label: t('Only students using transport') },
                    { on: isMandatory, set: setIsMandatory, label: t('Mandatory') },
                    { on: isRefundable, set: setIsRefundable, label: t('Refundable') },
                    { on: isActive, set: setIsActive, label: t('Active') },
                  ].map((row) => (
                    <label
                      key={row.label}
                      className="flex min-h-[44px] items-center gap-3 rounded-lg border border-gray-100 px-3"
                    >
                      <input
                        type="checkbox"
                        checked={row.on}
                        onChange={(e) => row.set(e.target.checked)}
                        className="h-5 w-5 rounded border-gray-300 text-blue-600"
                      />
                      <span className="text-sm text-gray-800">{row.label}</span>
                    </label>
                  ))}
                </div>
              </FieldWide>
            </FieldGrid>

            {editing.is_system && (
              <p className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
                {t('This is a seeded head. It can be switched off but not deleted — invoices point at it.')}
              </p>
            )}
          </div>
        )}
      </BaseModal>
    </div>
  );
}
