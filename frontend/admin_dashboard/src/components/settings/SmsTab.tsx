import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { apiClient } from '../../lib/api';
import type { Branch, MessageTemplate, SmsMessage, TemplatePlaceholders } from '../../lib/api';
import { apiErrorText } from '../../lib/apiErrors';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { formatNumber } from '../../lib/format';
import { formatDhakaDateTime } from '../../lib/timezone';
import { useRequestId } from '../../lib/useRequestId';
import Field, { FormError } from '../common/Field';
import ResponsiveTable from '../common/ResponsiveTable';
import type { Column } from '../common/ResponsiveTable';
import { btnPrimary, btnSecondary, inputCls } from '../common/styles';

/**
 * SMS — the switch, the name on the handset, the wording, and what was sent.
 *
 * The four things an institution needs in one place, because they are one
 * question: *what do our guardians receive, and did they?*
 *
 * The wording editor counts the message **in billable SMS, not characters**. A
 * Bengali body is Unicode, so it crosses from one SMS to two at 70 characters
 * and the writer cannot be expected to know that — an institution that adds its
 * own name to the end of a result message doubles its results-day bill, and it
 * should find that out while typing rather than on an invoice.
 */

const EVENT = 'result_published';

/** A titled panel. NOT `common/SectionCard`, which is a preview-and-button
 *  tile for a settings checklist and ignores children — this screen's sections
 *  are edited in place, because the wording and the switch are two lines each
 *  and a modal for either would be a door in front of a door. */
function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm sm:p-5">
      <h3 className="mb-3 text-sm font-semibold text-gray-900">{title}</h3>
      {children}
    </section>
  );
}

export default function SmsTab({ branchId }: { branchId: number | null }) {
  const { t } = useT();
  const { can } = usePermissions();
  const mayEdit = can('settings', 'update');

  const [branch, setBranch] = useState<Branch | null>(null);
  const [template, setTemplate] = useState<MessageTemplate | null>(null);
  const [guide, setGuide] = useState<TemplatePlaceholders | null>(null);
  const [outbox, setOutbox] = useState<SmsMessage[]>([]);

  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const req = useRequestId();

  const load = useCallback(async () => {
    const mine = req.begin();
    if (!branchId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [branches, templates, placeholders, messages] = await Promise.all([
        apiClient.getBranches(),
        apiClient.listAll<MessageTemplate>('/message-templates/', `?event=${EVENT}`),
        apiClient.templatePlaceholders(),
        apiClient.list<SmsMessage>('/sms/', '?ordering=-created_at'),
      ]);
      if (!req.isCurrent(mine)) return;

      const own = branches.find((b) => b.id === branchId) ?? null;
      const language = own?.default_language === 'en' ? 'en' : 'bn';
      const mineTemplate = templates.find((row) => row.language === language) ?? null;

      setBranch(own);
      setTemplate(mineTemplate);
      setGuide(placeholders);
      setOutbox(messages.results);
      setBody(
        mineTemplate?.body
        // The built-in wording, so the box is never empty and "save" always
        // means "this is what we send" rather than "start from nothing".
        ?? placeholders.defaults.find(
          (d) => d.event === EVENT && d.language === language,
        )?.body
        ?? '',
      );
    } catch (err) {
      if (!req.isCurrent(mine)) return;
      setError(apiErrorText(err, t, t('Could not load the SMS settings.')));
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [branchId, req, t]);

  // Deferred by a tick rather than called from the effect body: `load` sets
  // state synchronously, which during an effect cascades a render before the
  // first paint. The same shape every other list screen here uses.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  /** What this wording costs, counted the way the gateway counts it. */
  const cost = useMemo(() => {
    // One character outside ASCII sends the WHOLE message as Unicode — which
    // is every Bengali message, and the reason the limit halves from 160 to 70.
    const unicode = [...body].some((ch) => (ch.codePointAt(0) ?? 0) > 127);
    const single = unicode ? 70 : 160;
    const multi = unicode ? 67 : 153;
    const length = body.length;
    const parts = length <= single ? 1 : Math.ceil(length / multi);
    return { unicode, length, single, parts };
  }, [body]);

  const saveSwitch = async (patch: Partial<Branch>) => {
    if (!branch) return;
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      setBranch(await apiClient.updateBranch(branch.id, patch));
      setSaved(t('Saved'));
    } catch (err) {
      setError(apiErrorText(err, t, t('That could not be saved.')));
    } finally {
      setSaving(false);
    }
  };

  const saveTemplate = async () => {
    if (!branch || saving) return;
    setSaving(true);
    setError(null);
    setSaved(null);
    const language = branch.default_language === 'en' ? 'en' : 'bn';
    try {
      const payload = { event: EVENT, channel: 'sms', language, body: body.trim(), is_active: true };
      const row = template
        ? await apiClient.patch<MessageTemplate>('/message-templates/', template.id, payload)
        : await apiClient.create<MessageTemplate>('/message-templates/', payload);
      setTemplate(row);
      setSaved(t('Saved'));
    } catch (err) {
      setError(apiErrorText(err, t, t('The message could not be saved.')));
    } finally {
      setSaving(false);
    }
  };

  const columns: Column<SmsMessage>[] = [
    {
      key: 'when',
      label: t('When'),
      primary: true,
      render: (row) => formatDhakaDateTime(row.sent_at ?? row.created_at),
    },
    {
      key: 'to',
      label: t('To'),
      render: (row) => (
        <span className="block">
          <span className="font-mono text-[13px]">{row.to_phone || '—'}</span>
          {row.recipient_label && (
            <span className="block text-xs text-gray-500">{row.recipient_label}</span>
          )}
        </span>
      ),
    },
    { key: 'student', label: t('Student'), render: (row) => row.student_name || '—' },
    {
      key: 'status',
      label: t('Status'),
      render: (row) => (
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
            row.status === 'sent'
              ? 'bg-green-50 text-green-700'
              : row.status === 'failed'
                ? 'bg-red-50 text-red-700'
                : row.status === 'skipped'
                  ? 'bg-gray-100 text-gray-600'
                  : 'bg-amber-50 text-amber-800'
          }`}
        >
          {row.status_display}
        </span>
      ),
    },
    {
      key: 'why',
      label: t('Provider'),
      hideOnNarrow: true,
      // The gateway's own words — "Balance Insufficient" is an answer somebody
      // can act on, and a generic "failed" is not.
      render: (row) => row.provider_message || row.skip_reason || '—',
    },
    { key: 'parts', label: t('SMS'), hideOnNarrow: true, render: (row) => formatNumber(row.parts) },
  ];

  if (!branchId) {
    return (
      <Panel title={t('SMS')}>
        <p className="text-sm text-gray-500">
          {t('Choose an institution in the header to set up its SMS.')}
        </p>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      <FormError message={error} />
      {saved && (
        <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">{saved}</p>
      )}

      <Panel title={t('Sending')}>
        <div className="space-y-4">
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 h-5 w-5 shrink-0 rounded border-gray-300 text-blue-600"
              checked={branch?.sms_enabled ?? true}
              disabled={!mayEdit || saving}
              onChange={(e) => void saveSwitch({ sms_enabled: e.target.checked })}
            />
            <span>
              <span className="block text-sm font-medium text-gray-900">
                {t('Send SMS to guardians')}
              </span>
              <span className="block text-xs text-gray-500">
                {t('Off means nothing leaves this institution, whatever a screen offers.')}
              </span>
            </span>
          </label>

          <Field
            label={t('Sender name')}
            hint={t('What the guardian sees the message is from. Registered with the SMS operator; left blank, the platform’s own name is used.')}
          >
            <input
              className={inputCls}
              maxLength={20}
              defaultValue={branch?.sms_sender_id ?? ''}
              disabled={!mayEdit || saving}
              onBlur={(e) => {
                const next = e.target.value.trim();
                if (next !== (branch?.sms_sender_id ?? '')) void saveSwitch({ sms_sender_id: next });
              }}
            />
          </Field>
        </div>
      </Panel>

      <Panel title={t('What a result message says')}>
        <div className="space-y-3">
          <textarea
            className={`${inputCls} min-h-[96px]`}
            value={body}
            disabled={!mayEdit}
            onChange={(e) => setBody(e.target.value)}
          />

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span
              className={`inline-flex rounded-full px-2 py-0.5 font-medium ${
                cost.parts > 1 ? 'bg-amber-50 text-amber-800' : 'bg-gray-100 text-gray-600'
              }`}
            >
              {`${formatNumber(cost.length)} / ${formatNumber(cost.single)} · ${formatNumber(cost.parts)} ${t('SMS per student')}`}
            </span>
            <span className="text-gray-500">
              {cost.unicode
                ? t('Bangla is sent as Unicode: 70 characters to one SMS.')
                : t('English only: 160 characters to one SMS.')}
            </span>
          </div>

          {guide && (
            <div className="flex flex-wrap gap-1.5">
              {(guide.placeholders[EVENT] ?? []).map((p) => (
                <button
                  key={p.name}
                  type="button"
                  disabled={!mayEdit}
                  onClick={() => setBody((prev) => `${prev}{${p.name}}`)}
                  className="rounded-md border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
                  title={p.label}
                >
                  {`{${p.name}}`}
                </button>
              ))}
            </div>
          )}

          {mayEdit && (
            <div className="flex gap-2">
              <button
                type="button"
                className={btnSecondary}
                onClick={() => {
                  const language = branch?.default_language === 'en' ? 'en' : 'bn';
                  setBody(guide?.defaults.find(
                    (d) => d.event === EVENT && d.language === language,
                  )?.body ?? '');
                }}
              >
                {t('Use the default wording')}
              </button>
              <button
                type="button"
                className={btnPrimary}
                disabled={saving || !body.trim()}
                onClick={() => void saveTemplate()}
              >
                {saving ? t('Saving…') : t('Save message')}
              </button>
            </div>
          )}
        </div>
      </Panel>

      <Panel title={t('Recently sent')}>
        <ResponsiveTable
          columns={columns}
          rows={outbox}
          rowKey={(row) => row.id}
          empty={loading ? t('Loading…') : t('Nothing has been sent yet.')}
        />
      </Panel>
    </div>
  );
}
