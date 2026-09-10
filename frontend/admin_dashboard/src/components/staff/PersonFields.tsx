import { useT } from '../../lib/i18n';
import Field, { FieldGrid, FieldWide } from '../common/Field';
import { inputCls, selectCls } from '../common/styles';
import { BLOOD_GROUPS, EMPLOYMENT_STATUSES, GENDERS } from './shared';
import type { PersonDraft } from './shared';

/**
 * The shared half of the teacher and employee forms.
 *
 * A component rather than a copied block: the two records are separate tables
 * by design (`docs/08` D5), and the one thing that must NOT diverge with them is
 * how the same person is asked for.
 */
export default function PersonFields({
  draft,
  onChange,
  errors,
}: {
  draft: PersonDraft;
  onChange: (next: PersonDraft) => void;
  errors: Record<string, string>;
}) {
  const { t } = useT();
  const set = (patch: Partial<PersonDraft>) => onChange({ ...draft, ...patch });

  return (
    <div className="space-y-4">
      <FieldGrid>
        <Field label={t('Name (English)')} error={errors.name} required>
          <input value={draft.name} onChange={(e) => set({ name: e.target.value })} className={inputCls} />
        </Field>
        <Field label={t('Name (Bangla)')} error={errors.name_bn} required>
          <input value={draft.name_bn} onChange={(e) => set({ name_bn: e.target.value })} className={inputCls} />
        </Field>
        <Field label={t('Designation')} error={errors.designation} required>
          <input
            value={draft.designation}
            onChange={(e) => set({ designation: e.target.value })}
            className={inputCls}
          />
        </Field>
        <Field label={t('Joining date')} error={errors.joining_date} required>
          <input
            type="date"
            value={draft.joining_date}
            onChange={(e) => set({ joining_date: e.target.value })}
            className={inputCls}
          />
        </Field>
        <Field label={t('Mobile')} error={errors.phone}>
          <input
            type="tel"
            inputMode="numeric"
            value={draft.phone}
            onChange={(e) => set({ phone: e.target.value })}
            className={inputCls}
          />
        </Field>
        <Field label={t('Alternate mobile')} error={errors.alt_phone}>
          <input
            type="tel"
            inputMode="numeric"
            value={draft.alt_phone}
            onChange={(e) => set({ alt_phone: e.target.value })}
            className={inputCls}
          />
        </Field>
        <Field label={t('Email')} error={errors.email}>
          <input
            type="email"
            value={draft.email}
            onChange={(e) => set({ email: e.target.value })}
            className={inputCls}
          />
        </Field>
        <Field label={t('Date of birth')} error={errors.dob}>
          <input type="date" value={draft.dob} onChange={(e) => set({ dob: e.target.value })} className={inputCls} />
        </Field>
        <Field label={t('Gender')} error={errors.gender}>
          <select
            value={draft.gender}
            onChange={(e) => set({ gender: e.target.value as PersonDraft['gender'] })}
            className={selectCls}
          >
            <option value="">{t('Not stated')}</option>
            {GENDERS.map((g) => (
              <option key={g.value} value={g.value}>
                {t(g.label)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('NID')} error={errors.nid}>
          <input value={draft.nid} onChange={(e) => set({ nid: e.target.value })} className={inputCls} />
        </Field>
        <Field label={t('Blood group')} error={errors.blood_group}>
          <select
            value={draft.blood_group}
            onChange={(e) => set({ blood_group: e.target.value })}
            className={selectCls}
          >
            <option value="">{t('Not stated')}</option>
            {BLOOD_GROUPS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('Employment status')} error={errors.employment_status}>
          <select
            value={draft.employment_status}
            onChange={(e) => set({ employment_status: e.target.value as PersonDraft['employment_status'] })}
            className={selectCls}
          >
            {EMPLOYMENT_STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {t(s.label)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t('Leaving date')} error={errors.leaving_date}>
          <input
            type="date"
            value={draft.leaving_date}
            onChange={(e) => set({ leaving_date: e.target.value })}
            className={inputCls}
          />
        </Field>
      </FieldGrid>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{t('Address')}</h3>
        <FieldGrid>
          <Field label={t('Village / area')} error={errors.village}>
            <input value={draft.village} onChange={(e) => set({ village: e.target.value })} className={inputCls} />
          </Field>
          <Field label={t('Post office')} error={errors.post_office}>
            <input
              value={draft.post_office}
              onChange={(e) => set({ post_office: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Upazila / thana')} error={errors.upazila}>
            <input value={draft.upazila} onChange={(e) => set({ upazila: e.target.value })} className={inputCls} />
          </Field>
          <Field label={t('District')} error={errors.district}>
            <input value={draft.district} onChange={(e) => set({ district: e.target.value })} className={inputCls} />
          </Field>
          <FieldWide>
            <Field label={t('Other address details')} error={errors.address}>
              <input value={draft.address} onChange={(e) => set({ address: e.target.value })} className={inputCls} />
            </Field>
          </FieldWide>
        </FieldGrid>
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{t('Pay')}</h3>
        <FieldGrid>
          <Field label={t('Basic salary')} error={errors.basic_salary}>
            <input
              type="text"
              inputMode="decimal"
              value={draft.basic_salary}
              onChange={(e) => set({ basic_salary: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Allowances')} error={errors.allowances}>
            <input
              type="text"
              inputMode="decimal"
              value={draft.allowances}
              onChange={(e) => set({ allowances: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Deductions')} error={errors.deductions}>
            <input
              type="text"
              inputMode="decimal"
              value={draft.deductions}
              onChange={(e) => set({ deductions: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Bank account')} error={errors.bank_account}>
            <input
              value={draft.bank_account}
              onChange={(e) => set({ bank_account: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Mobile banking')} error={errors.mobile_banking}>
            <input
              value={draft.mobile_banking}
              onChange={(e) => set({ mobile_banking: e.target.value })}
              className={inputCls}
            />
          </Field>
        </FieldGrid>
      </section>

      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
          {t('Emergency contact')}
        </h3>
        <FieldGrid>
          <Field label={t('Name')} error={errors.emergency_contact_name}>
            <input
              value={draft.emergency_contact_name}
              onChange={(e) => set({ emergency_contact_name: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Mobile')} error={errors.emergency_contact_phone}>
            <input
              type="tel"
              inputMode="numeric"
              value={draft.emergency_contact_phone}
              onChange={(e) => set({ emergency_contact_phone: e.target.value })}
              className={inputCls}
            />
          </Field>
          <FieldWide>
            {/* 44px tall on a phone (§7a rule 4), no taller than a field above it. */}
            <label className="flex min-h-[44px] items-center gap-3 sm:min-h-[36px]">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(e) => set({ is_active: e.target.checked })}
                className="h-5 w-5 rounded border-gray-300 text-blue-600"
              />
              <span className="text-sm text-gray-700">{t('Active')}</span>
            </label>
          </FieldWide>
        </FieldGrid>
      </section>
    </div>
  );
}
