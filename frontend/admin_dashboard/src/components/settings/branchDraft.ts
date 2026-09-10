import type { Branch, InstitutionType } from '../../lib/api';

/**
 * The institution form's data, kept apart from the form itself.
 *
 * Everything here is a plain value or a pure function, and a module that
 * exports those beside a component costs Fast Refresh for every file that
 * imports it. It also lets a screen convert a `Branch` without pulling the
 * whole form in.
 *
 * The draft holds every numeric field as a **string**, deliberately: an input
 * that coerces while it is being typed cannot hold an empty value, so
 * backspacing over the last digit would write a 0 nobody typed. The conversion
 * happens once, in `draftToPayload`.
 */

export interface BranchDraft {
  name: string;
  name_bn: string;
  name_ar: string;
  institution_type: InstitutionType;
  code: string;
  established_year: string;
  address: string;
  address_bn: string;
  district: string;
  thana: string;
  phone: string;
  alt_phone: string;
  email: string;
  restrict_teachers_to_assigned_classes: boolean;
  attendance_window_minutes: string;
  activity_retention_days: string;
  weekly_off_days: string[];
  fine_per_day: string;
  fine_grace_days: string;
  fine_max: string;
  is_active: boolean;
}

export const INSTITUTION_TYPES: InstitutionType[] = ['madrasah', 'school', 'college', 'combined'];

/** Three-letter keys, exactly as the API stores and the attendance grid reads
 *  them. The label beside each is translated; the value never is. */
export const WEEK_DAYS = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri'] as const;

export const DAY_LABELS: Record<string, string> = {
  sat: 'Saturday',
  sun: 'Sunday',
  mon: 'Monday',
  tue: 'Tuesday',
  wed: 'Wednesday',
  thu: 'Thursday',
  fri: 'Friday',
};

export const TYPE_LABELS: Record<InstitutionType, string> = {
  madrasah: 'Madrasah',
  school: 'School',
  college: 'College',
  combined: 'Combined',
};

export function emptyDraft(): BranchDraft {
  return {
    name: '',
    name_bn: '',
    name_ar: '',
    institution_type: 'madrasah',
    code: '',
    established_year: '',
    address: '',
    address_bn: '',
    district: '',
    thana: '',
    phone: '',
    alt_phone: '',
    email: '',
    restrict_teachers_to_assigned_classes: true,
    attendance_window_minutes: '120',
    activity_retention_days: '180',
    weekly_off_days: ['fri'],
    fine_per_day: '0',
    fine_grace_days: '0',
    fine_max: '0',
    is_active: true,
  };
}

export function draftFrom(branch: Branch): BranchDraft {
  const fine = (branch.fine_rule ?? {}) as Record<string, unknown>;
  return {
    name: branch.name ?? '',
    name_bn: branch.name_bn ?? '',
    name_ar: branch.name_ar ?? '',
    institution_type: branch.institution_type,
    code: branch.code ?? '',
    established_year: branch.established_year ? String(branch.established_year) : '',
    address: branch.address ?? '',
    address_bn: branch.address_bn ?? '',
    district: branch.district ?? '',
    thana: branch.thana ?? '',
    phone: branch.phone ?? '',
    alt_phone: branch.alt_phone ?? '',
    email: branch.email ?? '',
    restrict_teachers_to_assigned_classes: branch.restrict_teachers_to_assigned_classes ?? true,
    attendance_window_minutes: String(branch.attendance_window_minutes ?? 120),
    activity_retention_days: String(branch.activity_retention_days ?? 180),
    weekly_off_days: branch.weekly_off_days ?? ['fri'],
    fine_per_day: String(fine.per_day ?? 0),
    fine_grace_days: String(fine.grace_days ?? 0),
    fine_max: String(fine.max ?? 0),
    is_active: branch.is_active ?? true,
  };
}

/** The draft as the API takes it. Numbers are parsed here rather than in the
 *  inputs: an input that coerces while it is being typed cannot hold an empty
 *  string, so backspacing over the last digit writes a 0 the user did not. */
export function draftToPayload(draft: BranchDraft, includePolicy: boolean): Partial<Branch> {
  const base: Partial<Branch> = {
    name: draft.name.trim(),
    name_bn: draft.name_bn.trim(),
    name_ar: draft.name_ar.trim(),
    institution_type: draft.institution_type,
    code: draft.code.trim().toUpperCase(),
    established_year: draft.established_year ? Number(draft.established_year) : null,
    address: draft.address.trim(),
    address_bn: draft.address_bn.trim(),
    district: draft.district.trim(),
    thana: draft.thana.trim(),
    phone: draft.phone.trim(),
    alt_phone: draft.alt_phone.trim(),
    email: draft.email.trim(),
  };

  if (!includePolicy) return base;

  return {
    ...base,
    is_active: draft.is_active,
    restrict_teachers_to_assigned_classes: draft.restrict_teachers_to_assigned_classes,
    attendance_window_minutes: Number(draft.attendance_window_minutes || 0),
    activity_retention_days: Number(draft.activity_retention_days || 0),
    weekly_off_days: draft.weekly_off_days,
    fine_rule: {
      per_day: Number(draft.fine_per_day || 0),
      grace_days: Number(draft.fine_grace_days || 0),
      max: Number(draft.fine_max || 0),
    },
  };
}
