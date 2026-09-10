import { useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Period, Stream } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import { shortTime, timeInputValue } from './shared';

/**
 * The bell schedule, on the Routine tab because that is what it shapes.
 *
 * Periods are the routine's rows: adding one adds a row to **every** class's
 * week, and moving one moves every lesson in it. That consequence is stated on
 * the screen rather than left to be discovered after the fact, which is also
 * why this sits here and not behind Settings.
 */
export default function PeriodsPanel({
  periods,
  streams,
  onChanged,
}: {
  periods: Period[];
  streams: Stream[];
  onChanged: () => Promise<void>;
}) {
  const { t } = useT();
  const { can } = usePermissions();

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Period | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const mayCreate = can('academics', 'create');
  const mayUpdate = can('academics', 'update');
  const mayDelete = can('academics', 'delete');

  const blank = (): Period => ({
    id: 0,
    stream: null,
    name: '',
    name_bn: '',
    order: periods.length + 1,
    start_time: '',
    end_time: '',
    is_break: false,
    is_active: true,
  });

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      stream: draft.stream,
      name: draft.name.trim(),
      name_bn: draft.name_bn.trim(),
      order: draft.order,
      start_time: draft.start_time,
      end_time: draft.end_time,
      is_break: draft.is_break,
      is_active: draft.is_active,
    };
    try {
      if (draft.id) await apiClient.patch<Period>('/periods/', draft.id, body);
      else await apiClient.create<Period>('/periods/', body);
      setDraft(null);
      await onChanged();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this period.')));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (period: Period) => {
    if (!window.confirm(t('Delete this period? Every lesson scheduled in it is removed with it.'))) return;
    try {
      await apiClient.destroy('/periods/', period.id);
      await onChanged();
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not delete this period.')));
    }
  };

  const streamName = (id: number | null) => {
    if (id === null) return t('Every stream');
    const stream = streams.find((s) => s.id === id);
    return stream ? stream.name_bn || stream.name : '—';
  };

  return (
    <section className="rounded-xl border border-gray-100 bg-white shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((x) => !x)}
        className="flex min-h-[56px] w-full items-center justify-between gap-3 px-4 text-left"
        aria-expanded={open}
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-gray-900">{t('Periods (bell schedule)')}</span>
          <span className="block truncate text-xs text-gray-500">
            {periods.length > 0
              ? periods
                  .map((p) => `${p.name_bn || p.name} ${shortTime(p.start_time)}`)
                  .join(' · ')
              : t('No periods yet — the routine grid has no rows until one exists.')}
          </span>
        </span>
        <span className="shrink-0 text-gray-400">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-gray-100 px-4 py-4">
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900">
            {t('These times are the rows of every class’s week. Changing one moves that period for the whole institution.')}
          </p>

          <ul className="divide-y divide-gray-100">
            {periods.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-gray-900">
                    {p.name_bn || p.name}
                    {p.is_break && (
                      <span className="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                        {t('Break')}
                      </span>
                    )}
                  </span>
                  <span className="block text-xs text-gray-500">
                    {shortTime(p.start_time)}–{shortTime(p.end_time)} · {streamName(p.stream)}
                  </span>
                </span>
                {mayUpdate && (
                  <button type="button" onClick={() => setDraft(p)} className={btnSecondary}>
                    {t('Edit')}
                  </button>
                )}
                {mayDelete && (
                  <button
                    type="button"
                    onClick={() => void remove(p)}
                    className="tap rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50"
                  >
                    {t('Delete')}
                  </button>
                )}
              </li>
            ))}
          </ul>

          {mayCreate && (
            <button type="button" onClick={() => setDraft(blank())} className={`${btnPrimary} w-full sm:w-auto`}>
              {t('Add period')}
            </button>
          )}
        </div>
      )}

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={draft?.id ? t('Edit period') : t('Add period')}
        maxWidth="lg"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button type="button" onClick={() => void save()} disabled={saving} className={`${btnPrimary} flex-1`}>
              {saving ? t('Saving…') : t('Save')}
            </button>
          </div>
        }
      >
        {draft && (
          <div className="space-y-4">
            <FormError message={formError} />
            <FieldGrid>
              <Field label={t('Name (English)')} error={fieldErrors.name} required>
                <input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Name (Bangla)')} error={fieldErrors.name_bn} required>
                <input
                  value={draft.name_bn}
                  onChange={(e) => setDraft({ ...draft, name_bn: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Starts')} error={fieldErrors.start_time} required>
                <input
                  type="time"
                  value={timeInputValue(draft.start_time)}
                  onChange={(e) => setDraft({ ...draft, start_time: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Ends')} error={fieldErrors.end_time} required>
                <input
                  type="time"
                  value={timeInputValue(draft.end_time)}
                  onChange={(e) => setDraft({ ...draft, end_time: e.target.value })}
                  className={inputCls}
                />
              </Field>
              <Field label={t('Order')} error={fieldErrors.order} required>
                <input
                  type="number"
                  inputMode="numeric"
                  value={draft.order}
                  onChange={(e) => setDraft({ ...draft, order: Number(e.target.value || 0) })}
                  className={inputCls}
                />
              </Field>
              <Field
                label={t('Stream')}
                hint={t('Leave blank when the whole institution rings the same bell.')}
                error={fieldErrors.stream}
              >
                <select
                  value={draft.stream === null ? '' : String(draft.stream)}
                  onChange={(e) =>
                    setDraft({ ...draft, stream: e.target.value ? Number(e.target.value) : null })
                  }
                  className={selectCls}
                >
                  <option value="">{t('Every stream')}</option>
                  {streams.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name_bn || s.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('Break')}>
                <label className="flex min-h-[44px] items-center gap-3">
                  <input
                    type="checkbox"
                    checked={draft.is_break}
                    onChange={(e) => setDraft({ ...draft, is_break: e.target.checked })}
                    className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  />
                  <span className="text-sm text-gray-700">{t('Nothing is taught in this period')}</span>
                </label>
              </Field>
            </FieldGrid>
          </div>
        )}
      </BaseModal>
    </section>
  );
}
