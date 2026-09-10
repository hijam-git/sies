import { useState } from 'react';
import type { FormEvent } from 'react';
import type { InstitutionType } from '../../lib/api';
import { useT } from '../../lib/i18n';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import { btnPrimary, inputCls, selectCls } from '../common/styles';
import { DAY_LABELS, INSTITUTION_TYPES, TYPE_LABELS, WEEK_DAYS } from './branchDraft';
import type { BranchDraft } from './branchDraft';

/**
 * The institution form — used to open one and to edit one.
 *
 * One component for both because `docs/08` D1 consequence 2 asks for onboarding
 * as "one screen, one transaction": the fields an admin fills in to create an
 * institution are the fields they later correct, and two forms would drift into
 * disagreeing about which of them is required.
 *
 * The policy block is shown only when editing. Its four settings (D6, D7, D8)
 * all have sensible defaults the backend applies at creation, and asking an
 * operator to decide the attendance window before the institution has a single
 * teacher is asking a question nobody can answer yet.
 */


export default function BranchForm({
  draft,
  setDraft,
  onSubmit,
  onCancel,
  saving,
  formError,
  fieldErrors,
  mode,
}: {
  draft: BranchDraft;
  setDraft: (next: BranchDraft) => void;
  onSubmit: () => void;
  onCancel?: () => void;
  saving: boolean;
  formError: string | null;
  fieldErrors: Record<string, string>;
  mode: 'create' | 'edit';
}) {
  const { t } = useT();
  const [policyOpen, setPolicyOpen] = useState(false);

  const set = <K extends keyof BranchDraft>(key: K, value: BranchDraft[K]) =>
    setDraft({ ...draft, [key]: value });

  const toggleDay = (day: string) => {
    const next = draft.weekly_off_days.includes(day)
      ? draft.weekly_off_days.filter((d) => d !== day)
      : [...draft.weekly_off_days, day];
    set('weekly_off_days', next);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit();
  };

  return (
    <form id="branch-form" onSubmit={handleSubmit} className="space-y-5">
      <FormError message={formError} />

      <FieldGrid>
        <Field label={t('Name (English)')} required error={fieldErrors.name}>
          <input
            className={inputCls}
            value={draft.name}
            onChange={(e) => set('name', e.target.value)}
            required
            autoComplete="off"
          />
        </Field>

        <Field label={t('Name (Bangla)')} error={fieldErrors.name_bn}>
          <input
            className={inputCls}
            value={draft.name_bn}
            onChange={(e) => set('name_bn', e.target.value)}
            lang="bn"
          />
        </Field>

        <Field
          label={t('Name (Arabic)')}
          hint={t('Shown on certificates and the printed form')}
          error={fieldErrors.name_ar}
        >
          <input
            className={inputCls}
            dir="rtl"
            lang="ar"
            value={draft.name_ar}
            onChange={(e) => set('name_ar', e.target.value)}
          />
        </Field>

        <Field
          label={t('Institution type')}
          required
          hint={t('Selects which streams and defaults get seeded')}
          error={fieldErrors.institution_type}
        >
          <select
            className={selectCls}
            value={draft.institution_type}
            onChange={(e) => set('institution_type', e.target.value as InstitutionType)}
            disabled={mode === 'edit'}
          >
            {INSTITUTION_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(TYPE_LABELS[type])}
              </option>
            ))}
          </select>
        </Field>

        <Field
          label={t('Code')}
          required
          hint={t('Short and unique — it prefixes every admission and receipt number')}
          error={fieldErrors.code}
        >
          <input
            className={`${inputCls} uppercase`}
            value={draft.code}
            onChange={(e) => set('code', e.target.value.toUpperCase())}
            required
            maxLength={20}
            autoComplete="off"
          />
        </Field>

        <Field label={t('Established year')} error={fieldErrors.established_year}>
          <input
            className={inputCls}
            value={draft.established_year}
            onChange={(e) => set('established_year', e.target.value.replace(/\D/g, '').slice(0, 4))}
            inputMode="numeric"
          />
        </Field>

        <FieldWide>
          <Field label={t('Address')} error={fieldErrors.address}>
            <textarea
              className={inputCls}
              rows={2}
              value={draft.address}
              onChange={(e) => set('address', e.target.value)}
            />
          </Field>
        </FieldWide>

        <Field label={t('District')} error={fieldErrors.district}>
          <input
            className={inputCls}
            value={draft.district}
            onChange={(e) => set('district', e.target.value)}
          />
        </Field>

        <Field label={t('Thana / Upazila')} error={fieldErrors.thana}>
          <input
            className={inputCls}
            value={draft.thana}
            onChange={(e) => set('thana', e.target.value)}
          />
        </Field>

        <Field label={t('Phone')} error={fieldErrors.phone}>
          <input
            className={inputCls}
            value={draft.phone}
            onChange={(e) => set('phone', e.target.value)}
            inputMode="tel"
          />
        </Field>

        <Field label={t('Email')} error={fieldErrors.email}>
          <input
            className={inputCls}
            type="email"
            value={draft.email}
            onChange={(e) => set('email', e.target.value)}
            inputMode="email"
          />
        </Field>
      </FieldGrid>

      {mode === 'edit' && (
        <section className="rounded-xl border border-gray-200">
          {/* Collapsed by default. These are the settings an institution sets
              once and then leaves alone, and putting them above the address
              would make the everyday edit scroll past the rare one. */}
          <button
            type="button"
            onClick={() => setPolicyOpen((o) => !o)}
            aria-expanded={policyOpen}
            className="flex min-h-[44px] w-full items-center justify-between gap-3 px-4 text-left"
          >
            <span className="text-sm font-semibold text-gray-900">
              {t('Attendance, fines and activity')}
            </span>
            <span className="text-gray-400">{policyOpen ? '−' : '+'}</span>
          </button>

          {policyOpen && (
            <div className="space-y-5 border-t border-gray-100 p-4">
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1 h-5 w-5 shrink-0 rounded border-gray-300 text-blue-600"
                  checked={draft.restrict_teachers_to_assigned_classes}
                  onChange={(e) => set('restrict_teachers_to_assigned_classes', e.target.checked)}
                />
                <span>
                  <span className="block text-sm font-medium text-gray-900">
                    {t('Teachers may only reach their assigned classes')}
                  </span>
                  <span className="mt-0.5 block text-xs text-gray-500">
                    {t(
                      'A small institution where everyone covers everything can switch this off.',
                    )}
                  </span>
                </span>
              </label>

              <FieldGrid>
                <Field
                  label={t('Attendance window (minutes)')}
                  hint={t('How long after a period starts a teacher may still mark it')}
                  error={fieldErrors.attendance_window_minutes}
                >
                  <input
                    className={inputCls}
                    value={draft.attendance_window_minutes}
                    onChange={(e) =>
                      set('attendance_window_minutes', e.target.value.replace(/\D/g, ''))
                    }
                    inputMode="numeric"
                  />
                </Field>

                <Field
                  label={t('Keep activity for (days)')}
                  hint={t('Older entries are pruned nightly')}
                  error={fieldErrors.activity_retention_days}
                >
                  <input
                    className={inputCls}
                    value={draft.activity_retention_days}
                    onChange={(e) =>
                      set('activity_retention_days', e.target.value.replace(/\D/g, ''))
                    }
                    inputMode="numeric"
                  />
                </Field>
              </FieldGrid>

              <fieldset>
                <legend className="mb-2 text-sm font-medium text-gray-700">
                  {t('Weekly off days')}
                </legend>
                {/* Wraps rather than scrolls: seven 44px chips fit two rows at
                    360px, and a scrolling row would hide the day at the end. */}
                <div className="flex flex-wrap gap-2">
                  {WEEK_DAYS.map((day) => {
                    const on = draft.weekly_off_days.includes(day);
                    return (
                      <button
                        key={day}
                        type="button"
                        aria-pressed={on}
                        onClick={() => toggleDay(day)}
                        className={`tap rounded-lg border px-3 text-sm font-medium ${
                          on
                            ? 'border-blue-600 bg-blue-50 text-blue-700'
                            : 'border-gray-200 bg-white text-gray-600'
                        }`}
                      >
                        {t(DAY_LABELS[day])}
                      </button>
                    );
                  })}
                </div>
              </fieldset>

              <div>
                <p className="mb-2 text-sm font-medium text-gray-700">{t('Late fee rule')}</p>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <Field label={t('Per day')}>
                    <input
                      className={inputCls}
                      value={draft.fine_per_day}
                      onChange={(e) => set('fine_per_day', e.target.value.replace(/[^\d.]/g, ''))}
                      inputMode="decimal"
                    />
                  </Field>
                  <Field label={t('Grace days')}>
                    <input
                      className={inputCls}
                      value={draft.fine_grace_days}
                      onChange={(e) => set('fine_grace_days', e.target.value.replace(/\D/g, ''))}
                      inputMode="numeric"
                    />
                  </Field>
                  <Field label={t('Maximum fine')}>
                    <input
                      className={inputCls}
                      value={draft.fine_max}
                      onChange={(e) => set('fine_max', e.target.value.replace(/[^\d.]/g, ''))}
                      inputMode="decimal"
                    />
                  </Field>
                </div>
              </div>

              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  className="h-5 w-5 rounded border-gray-300 text-blue-600"
                  checked={draft.is_active}
                  onChange={(e) => set('is_active', e.target.checked)}
                />
                <span className="text-sm font-medium text-gray-900">
                  {t('This institution is open')}
                </span>
              </label>
            </div>
          )}
        </section>
      )}

      {/* Rendered only when the form is NOT inside a modal — a modal supplies
          its own sticky footer, and two Save buttons on one form is a bug
          somebody has to think about before pressing either. */}
      {onCancel === undefined && (
        <div className="flex flex-wrap gap-2">
          <button type="submit" className={btnPrimary} disabled={saving}>
            {saving ? t('Saving...') : t('Save Changes')}
          </button>
        </div>
      )}
    </form>
  );
}
