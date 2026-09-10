import { useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Gender, Student, StudentStatus, Stream } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import ImageUploadField from '../common/ImageUploadField';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';
import { todayInDhaka } from '../../lib/timezone';

/**
 * Create or correct a student record — identity only.
 *
 * There is no class or section on this form, and that is not an omission: a
 * student's class lives on an Enrolment, one per session, and typing it here
 * would create a second answer to a question the register already answers.
 * A student reaches a class either by being admitted or by being enrolled.
 *
 * **The address is four fields.** Village, post office, upazila and district
 * each have their own box on the printed admission form, and a single joined
 * line cannot be taken apart again when the form is generated.
 */

const STATUSES: { value: StudentStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'passed_out', label: 'Passed out' },
  { value: 'withdrawn', label: 'Withdrawn' },
  { value: 'transferred', label: 'Transferred' },
];

const GENDERS: { value: Gender; label: string }[] = [
  { value: 'male', label: 'Boy' },
  { value: 'female', label: 'Girl' },
  { value: 'other', label: 'Other' },
];

const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];

interface StudentDraft {
  name: string;
  name_bn: string;
  stream: string;
  date_of_birth: string;
  gender: Gender | '';
  birth_certificate_no: string;
  nid: string;
  blood_group: string;
  phone: string;
  email: string;
  village: string;
  post_office: string;
  upazila: string;
  district: string;
  present_address: string;
  permanent_address: string;
  previous_institution: string;
  previous_class: string;
  admitted_on: string;
  status: StudentStatus;
  is_active: boolean;
}

const EMPTY: StudentDraft = {
  name: '',
  name_bn: '',
  stream: '',
  date_of_birth: '',
  gender: '',
  birth_certificate_no: '',
  nid: '',
  blood_group: '',
  phone: '',
  email: '',
  village: '',
  post_office: '',
  upazila: '',
  district: '',
  present_address: '',
  permanent_address: '',
  previous_institution: '',
  previous_class: '',
  // Today — a student is admitted on the day somebody types them in.
  // `AdmissionsTab` already seeds the same field this way; the two paths
  // disagreeing was the bug, not the default.
  admitted_on: todayInDhaka(),
  status: 'active',
  is_active: true,
};

function draftFrom(row: Student): StudentDraft {
  return {
    name: row.name,
    name_bn: row.name_bn,
    stream: row.stream === null ? '' : String(row.stream),
    date_of_birth: row.date_of_birth ?? '',
    gender: row.gender,
    birth_certificate_no: row.birth_certificate_no,
    nid: row.nid,
    blood_group: row.blood_group,
    phone: row.phone,
    email: row.email,
    village: row.village,
    post_office: row.post_office,
    upazila: row.upazila,
    district: row.district,
    present_address: row.present_address,
    permanent_address: row.permanent_address,
    previous_institution: row.previous_institution,
    previous_class: row.previous_class,
    admitted_on: row.admitted_on ?? '',
    status: row.status,
    is_active: row.is_active,
  };
}

export default function StudentFormModal({
  student,
  streams,
  onClose,
  onSaved,
}: {
  /** The record being corrected, or null for a new one. */
  student: Student | null;
  streams: Stream[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { t } = useT();
  const [draft, setDraft] = useState<StudentDraft>(student ? draftFrom(student) : { ...EMPTY });
  const [photo, setPhoto] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = (patch: Partial<StudentDraft>) => setDraft({ ...draft, ...patch });

  const save = async () => {
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      name: draft.name.trim(),
      name_bn: draft.name_bn.trim(),
      stream: draft.stream ? Number(draft.stream) : null,
      // Empty dates go as null: DRF reads "" on a DateField as invalid rather
      // than as "not set", so a student with no birthday recorded would fail.
      date_of_birth: draft.date_of_birth || null,
      gender: draft.gender,
      birth_certificate_no: draft.birth_certificate_no.trim(),
      nid: draft.nid.trim(),
      blood_group: draft.blood_group,
      phone: draft.phone.trim(),
      email: draft.email.trim(),
      village: draft.village.trim(),
      post_office: draft.post_office.trim(),
      upazila: draft.upazila.trim(),
      district: draft.district.trim(),
      present_address: draft.present_address.trim(),
      permanent_address: draft.permanent_address.trim(),
      previous_institution: draft.previous_institution.trim(),
      previous_class: draft.previous_class.trim(),
      admitted_on: draft.admitted_on || null,
      status: draft.status,
      is_active: draft.is_active,
    };
    try {
      const saved = student
        ? await apiClient.patch<Student>('/students/', student.id, body)
        : await apiClient.create<Student>('/students/', body);
      // The photo is a file, so it cannot ride in the JSON body — a second
      // request once there is a row to attach it to.
      if (photo) await apiClient.uploadPersonPhoto<Student>('/students/', saved.id, photo);
      await onSaved();
      onClose();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this student.')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title={student ? t('Edit student') : t('Add student')}
      maxWidth="4xl"
      footer={
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className={`${btnSecondary} flex-1`}>
            {t('Cancel')}
          </button>
          <button type="button" onClick={() => void save()} disabled={saving} className={`${btnPrimary} flex-1`}>
            {saving ? t('Saving…') : t('Save')}
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        <FormError message={formError} />

        <FieldGrid>
          <Field label={t('Name (English)')} error={fieldErrors.name} required>
            <input value={draft.name} onChange={(e) => set({ name: e.target.value })} className={inputCls} />
          </Field>
          <Field label={t('Name (Bangla)')} error={fieldErrors.name_bn} required>
            <input value={draft.name_bn} onChange={(e) => set({ name_bn: e.target.value })} className={inputCls} />
          </Field>
          <Field label={t('Stream')} error={fieldErrors.stream}>
            <select value={draft.stream} onChange={(e) => set({ stream: e.target.value })} className={selectCls}>
              <option value="">{t('Not stated')}</option>
              {streams.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name_bn || s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('Date of birth')} error={fieldErrors.date_of_birth}>
            <input
              type="date"
              value={draft.date_of_birth}
              onChange={(e) => set({ date_of_birth: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Gender')} error={fieldErrors.gender}>
            <select
              value={draft.gender}
              onChange={(e) => set({ gender: e.target.value as Gender | '' })}
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
          <Field label={t('Blood group')} error={fieldErrors.blood_group}>
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
          <Field label={t('Birth certificate no.')} error={fieldErrors.birth_certificate_no}>
            <input
              value={draft.birth_certificate_no}
              onChange={(e) => set({ birth_certificate_no: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('NID')} error={fieldErrors.nid}>
            <input value={draft.nid} onChange={(e) => set({ nid: e.target.value })} className={inputCls} />
          </Field>
          <Field
            label={t('Mobile')}
            hint={t('Most students have none. Leave it blank — a login is a separate action on the record.')}
            error={fieldErrors.phone}
          >
            <input
              type="tel"
              inputMode="numeric"
              value={draft.phone}
              onChange={(e) => set({ phone: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Email')} error={fieldErrors.email}>
            <input
              type="email"
              value={draft.email}
              onChange={(e) => set({ email: e.target.value })}
              className={inputCls}
            />
          </Field>
        </FieldGrid>

        <section>
          <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-500">{t('Address')}</h3>
          <p className="mb-3 text-xs text-gray-500">
            {t('Four separate boxes, because the printed admission form has a line for each.')}
          </p>
          <FieldGrid>
            <Field label={t('Village / area')} error={fieldErrors.village}>
              <input value={draft.village} onChange={(e) => set({ village: e.target.value })} className={inputCls} />
            </Field>
            <Field label={t('Post office')} error={fieldErrors.post_office}>
              <input
                value={draft.post_office}
                onChange={(e) => set({ post_office: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label={t('Upazila / thana')} error={fieldErrors.upazila}>
              <input value={draft.upazila} onChange={(e) => set({ upazila: e.target.value })} className={inputCls} />
            </Field>
            <Field label={t('District')} error={fieldErrors.district}>
              <input value={draft.district} onChange={(e) => set({ district: e.target.value })} className={inputCls} />
            </Field>
            <FieldWide>
              <Field label={t('Present address')} error={fieldErrors.present_address}>
                <input
                  value={draft.present_address}
                  onChange={(e) => set({ present_address: e.target.value })}
                  className={inputCls}
                />
              </Field>
            </FieldWide>
            <FieldWide>
              <Field label={t('Permanent address')} error={fieldErrors.permanent_address}>
                <input
                  value={draft.permanent_address}
                  onChange={(e) => set({ permanent_address: e.target.value })}
                  className={inputCls}
                />
              </Field>
            </FieldWide>
          </FieldGrid>
        </section>

        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            {t('Previous schooling')}
          </h3>
          <FieldGrid>
            <Field label={t('Previous institution')} error={fieldErrors.previous_institution}>
              <input
                value={draft.previous_institution}
                onChange={(e) => set({ previous_institution: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label={t('Previous class')} error={fieldErrors.previous_class}>
              <input
                value={draft.previous_class}
                onChange={(e) => set({ previous_class: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label={t('Admitted on')} error={fieldErrors.admitted_on}>
              <input
                type="date"
                value={draft.admitted_on}
                onChange={(e) => set({ admitted_on: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label={t('Status')} error={fieldErrors.status}>
              <select
                value={draft.status}
                onChange={(e) => set({ status: e.target.value as StudentStatus })}
                className={selectCls}
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {t(s.label)}
                  </option>
                ))}
              </select>
            </Field>
            <FieldWide>
              <label className="flex min-h-[44px] items-center gap-3">
                <input
                  type="checkbox"
                  checked={draft.is_active}
                  onChange={(e) => set({ is_active: e.target.checked })}
                  className="h-5 w-5 rounded border-gray-300 text-blue-600"
                />
                <span className="text-sm text-gray-700">{t('Record is in use')}</span>
              </label>
            </FieldWide>
          </FieldGrid>
        </section>

        <ImageUploadField
          label={t('Photograph')}
          value={student?.photo ?? ''}
          onChange={(file) => setPhoto(file)}
          helperText={t('Saved once the record exists.')}
        />
      </div>
    </BaseModal>
  );
}
