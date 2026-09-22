import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { ResultSmsPreview, ResultSmsSummary } from '../../lib/api';
import { apiErrorText } from '../../lib/apiErrors';
import { useT } from '../../lib/i18n';
import { formatNumber } from '../../lib/format';
import BaseModal from '../common/BaseModal';
import { FormError } from '../common/Field';
import { btnPrimary, btnSecondary } from '../common/styles';

/**
 * Sending an exam's results to the guardians' phones.
 *
 * **The preview is not decoration.** This button spends the institution's money
 * — a class of forty is forty SMS, and a Bengali body over 70 characters is
 * eighty — and it cannot be taken back the way unpublishing takes a result off
 * a screen. So the screen shows, before anything is sent: the exact message the
 * first guardian will receive, how many numbers are on file, how many messages
 * that comes to in billable parts, and the students whose guardian has no
 * number — because that list is the office's work for the afternoon, not an
 * error.
 *
 * Pressing send twice is safe (the outbox refuses a duplicate), and the screen
 * says so rather than relying on the reader knowing it.
 */
export default function SendResultSmsModal({
  examId,
  examLabel,
  academicClass,
  className,
  onClose,
}: {
  examId: number;
  examLabel: string;
  academicClass: number | null;
  className: string;
  onClose: () => void;
}) {
  const { t } = useT();

  const [preview, setPreview] = useState<ResultSmsPreview | null>(null);
  const [summary, setSummary] = useState<ResultSmsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPreview(await apiClient.previewResultSms(examId, academicClass));
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not work out what this send would cost.')));
    } finally {
      setLoading(false);
    }
  }, [examId, academicClass, t]);

  // Deferred by a tick rather than called from the effect body: `load` sets
  // state synchronously, which during an effect cascades a render before the
  // modal has painted. The same shape every list screen here uses.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  const send = async () => {
    if (sending) return;
    setSending(true);
    setError(null);
    try {
      const result = await apiClient.sendResultSms(examId, academicClass);
      setSummary(result);
      // The counts on screen are now history, so re-read: a second send would
      // be a different number, and showing the old one invites a second press.
      await load();
    } catch (err) {
      setError(apiErrorText(err, t, t('The results could not be sent.')));
    } finally {
      setSending(false);
    }
  };

  const nothingToSend = !!preview && preview.recipients === 0;

  return (
    <BaseModal isOpen title={t('Send results by SMS')} onClose={onClose} maxWidth="lg">
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          {examLabel}
          {className ? ` · ${className}` : ''}
        </p>

        <FormError message={error} />

        {loading && <p className="text-sm text-gray-400">{t('Loading…')}</p>}

        {preview && !preview.sms_enabled && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {t('SMS is switched off for this institution. Turn it on under Settings.')}
          </p>
        )}

        {summary && (
          <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
            {`${formatNumber(summary.queued)} ${t('messages queued')}`}
            {summary.already_sent
              ? ` · ${formatNumber(summary.already_sent)} ${t('already sent earlier')}`
              : ''}
            {summary.missing_phone
              ? ` · ${formatNumber(summary.missing_phone)} ${t('without a number')}`
              : ''}
          </p>
        )}

        {preview && (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Tile label={t('Guardians')} value={formatNumber(preview.recipients)} />
              <Tile
                label={t('Billable SMS')}
                value={formatNumber(preview.parts_total)}
                hint={preview.parts_total > preview.recipients
                  ? t('Some messages are longer than one SMS.')
                  : undefined}
              />
              <Tile
                label={t('No number')}
                value={formatNumber(preview.missing_phone.length)}
                tone={preview.missing_phone.length ? 'amber' : undefined}
              />
            </div>

            {/* The message itself, as the guardian will read it. */}
            <section className="rounded-xl border border-gray-200 bg-gray-50 p-3">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">
                {t('What the first guardian receives')}
                {preview.sender_id ? ` · ${t('from')} ${preview.sender_id}` : ''}
              </p>
              <p className="whitespace-pre-wrap break-words text-sm text-gray-900">
                {preview.sample || t('Nothing to send.')}
              </p>
            </section>

            {preview.already_sent > 0 && (
              <p className="text-sm text-gray-500">
                {`${formatNumber(preview.already_sent)} ${t('guardians already had this result — they will not be sent it twice.')}`}
              </p>
            )}

            {preview.missing_phone.length > 0 && (
              <section>
                <p className="mb-1 text-sm font-medium text-gray-700">
                  {t('No guardian number on file')}
                </p>
                <div className="scroll-x max-h-40 overflow-y-auto rounded-lg border border-gray-200">
                  <ul className="divide-y divide-gray-100 text-sm">
                    {preview.missing_phone.map((row) => (
                      <li key={row.student} className="flex gap-2 px-3 py-1.5">
                        <span className="w-10 shrink-0 text-gray-400">
                          {row.roll ?? '—'}
                        </span>
                        <span className="text-gray-800">{row.name}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  {t('Add a guardian phone on the student record, then send again — nobody is sent twice.')}
                </p>
              </section>
            )}
          </>
        )}

        <div className="flex gap-2">
          <button type="button" onClick={onClose} className={`${btnSecondary} flex-1`}>
            {summary ? t('Done') : t('Cancel')}
          </button>
          <button
            type="button"
            onClick={() => void send()}
            disabled={loading || sending || nothingToSend || !preview?.sms_enabled}
            className={`${btnPrimary} flex-1`}
          >
            {sending
              ? t('Sending…')
              : `${t('Send')} ${preview ? formatNumber(preview.recipients) : ''}`}
          </button>
        </div>
      </div>
    </BaseModal>
  );
}

function Tile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'amber';
}) {
  return (
    <div className="rounded-xl border border-gray-200/80 bg-white px-3 py-2">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-semibold ${tone === 'amber' ? 'text-amber-700' : 'text-gray-900'}`}>
        {value}
      </p>
      {hint && <p className="text-[11px] leading-snug text-gray-500">{hint}</p>}
    </div>
  );
}
