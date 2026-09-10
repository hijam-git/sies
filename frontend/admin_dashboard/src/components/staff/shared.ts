import type { EmploymentStatus, Gender, StaffPerson } from '../../lib/api';

/**
 * The half of a staff form that a teacher and an employee share.
 *
 * `Teacher` and `Employee` are separate models with separate tables (`docs/08`
 * D5), but the person on them is the same person — same name, same address,
 * same salary shape. Writing that half once here is what stops the two forms
 * drifting into asking for the address differently.
 */

export interface PersonDraft {
  name: string;
  name_bn: string;
  phone: string;
  alt_phone: string;
  email: string;
  dob: string;
  gender: Gender | '';
  nid: string;
  blood_group: string;
  // Four address fields and not one free-text box: the printed forms have a
  // line for each, and a joined string cannot be taken apart again.
  village: string;
  post_office: string;
  upazila: string;
  district: string;
  address: string;
  designation: string;
  joining_date: string;
  leaving_date: string;
  employment_status: EmploymentStatus;
  basic_salary: string;
  allowances: string;
  deductions: string;
  bank_account: string;
  mobile_banking: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  is_active: boolean;
}

export const EMPTY_PERSON: PersonDraft = {
  name: '',
  name_bn: '',
  phone: '',
  alt_phone: '',
  email: '',
  dob: '',
  gender: '',
  nid: '',
  blood_group: '',
  village: '',
  post_office: '',
  upazila: '',
  district: '',
  address: '',
  designation: '',
  joining_date: '',
  leaving_date: '',
  employment_status: 'active',
  basic_salary: '0',
  allowances: '0',
  deductions: '0',
  bank_account: '',
  mobile_banking: '',
  emergency_contact_name: '',
  emergency_contact_phone: '',
  is_active: true,
};

export function personDraftFrom(row: StaffPerson): PersonDraft {
  return {
    name: row.name,
    name_bn: row.name_bn,
    phone: row.phone,
    alt_phone: row.alt_phone,
    email: row.email,
    dob: row.dob ?? '',
    gender: row.gender,
    nid: row.nid,
    blood_group: row.blood_group,
    village: row.village,
    post_office: row.post_office,
    upazila: row.upazila,
    district: row.district,
    address: row.address,
    designation: row.designation,
    joining_date: row.joining_date ?? '',
    leaving_date: row.leaving_date ?? '',
    employment_status: row.employment_status,
    basic_salary: row.basic_salary,
    allowances: row.allowances,
    deductions: row.deductions,
    bank_account: row.bank_account,
    mobile_banking: row.mobile_banking,
    emergency_contact_name: row.emergency_contact_name,
    emergency_contact_phone: row.emergency_contact_phone,
    is_active: row.is_active,
  };
}

/**
 * The draft as the API wants it.
 *
 * Empty dates go as `null` rather than `""` — DRF reads an empty string on a
 * DateField as a validation error, not as "not set". Money goes as the typed
 * string: it is a Decimal server-side and a JS float is a rounding error
 * nobody can trace back.
 */
export function personBody(draft: PersonDraft): Record<string, unknown> {
  return {
    name: draft.name.trim(),
    name_bn: draft.name_bn.trim(),
    phone: draft.phone.trim(),
    alt_phone: draft.alt_phone.trim(),
    email: draft.email.trim(),
    dob: draft.dob || null,
    gender: draft.gender,
    nid: draft.nid.trim(),
    blood_group: draft.blood_group,
    village: draft.village.trim(),
    post_office: draft.post_office.trim(),
    upazila: draft.upazila.trim(),
    district: draft.district.trim(),
    address: draft.address.trim(),
    designation: draft.designation.trim(),
    joining_date: draft.joining_date || null,
    leaving_date: draft.leaving_date || null,
    employment_status: draft.employment_status,
    basic_salary: draft.basic_salary.trim() || '0',
    allowances: draft.allowances.trim() || '0',
    deductions: draft.deductions.trim() || '0',
    bank_account: draft.bank_account.trim(),
    mobile_banking: draft.mobile_banking.trim(),
    emergency_contact_name: draft.emergency_contact_name.trim(),
    emergency_contact_phone: draft.emergency_contact_phone.trim(),
    is_active: draft.is_active,
  };
}

export const EMPLOYMENT_STATUSES: { value: EmploymentStatus; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'on_leave', label: 'On leave' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'resigned', label: 'Resigned' },
  { value: 'terminated', label: 'Terminated' },
  { value: 'transferred', label: 'Transferred' },
];

export const GENDERS: { value: Gender; label: string }[] = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
];

export const BLOOD_GROUPS = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
