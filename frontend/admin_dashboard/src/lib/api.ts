/**
 * The one way this dashboard talks to the backend.
 *
 * Everything goes through `ApiClient.request`, which injects the JWT, retries
 * once behind a refresh on 401, and turns the API's single error shape into an
 * `ApiError`. Screens never call `fetch` themselves — a second call site is a
 * second place for a 401 to log somebody out at random.
 */

// Runtime API URL from window.ENV, written by the container at start rather
// than baked into the bundle. It is what lets one built image be promoted from
// staging to production: rebuilding to change a URL means the thing that was
// tested is not the thing that ships.
declare global {
  interface Window {
    ENV?: {
      API_URL?: string;
    };
  }
}

const getApiUrl = (): string => {
  return (typeof window !== 'undefined' && window.ENV?.API_URL) || '/api';
};

// ── Domain types ──────────────────────────────────────────────────────────

/** Who the person is. `docs/02` §1. */
export type UserType =
  | 'platform_admin'
  | 'platform_accountant'
  | 'principal'
  | 'accountant'
  | 'teacher'
  | 'employee'
  | 'student';

export type Language = 'bn' | 'en';

/** What kind of institution a branch is. Selects the seeded streams, classes
 *  and form template, and the labels the UI uses (`docs/08` D1). */
export type InstitutionType = 'madrasah' | 'school' | 'college' | 'combined';

/**
 * A branch is a whole institution — a school, a madrasah or a college — and
 * SIES is the platform they run on (`docs/08` D1). The word "branch" is kept
 * because it is the owner's word and renaming it later is churn.
 */
export interface Branch {
  id: number;
  name: string;
  name_bn: string;
  name_ar: string;
  code: string;
  institution_type: InstitutionType;
  /** `"Madrasah · মাদ্রাসা"` — both languages in one string, from the model's
   *  choice labels. Read-only. */
  institution_type_display?: string;
  address: string;
  address_bn: string;
  district: string;
  thana: string;
  phone: string;
  alt_phone: string;
  email: string;
  logo: string | null;
  established_year: number | null;
  is_active: boolean;

  // ── Policy. One endpoint serves both the switcher and the settings screen,
  // so these travel with the identity fields rather than in a second call.
  /** `docs/08` D6 — a teacher may only reach the classes assigned to them.
   *  Default on; a small institution where everyone covers everything can turn
   *  it off. */
  restrict_teachers_to_assigned_classes: boolean;
  /** `docs/08` D7 — how long after a period starts a teacher may still mark it. */
  attendance_window_minutes: number;
  /** `docs/08` D8 — the nightly prune's cut-off for the activity feed. */
  activity_retention_days: number;
  /** Three-letter day names, lower case: `["fri"]`. The month attendance grid
   *  reads this on every render. */
  weekly_off_days: string[];
  /** `{per_day, grace_days, max}`. Money, so every value is a plain number the
   *  backend stores as a Decimal — never arithmetic done here. */
  fine_rule: Record<string, number>;
  current_session: number | null;
  head: number | null;
  sms_sender_id: string;
  default_language: Language;
}

export interface User {
  id: number;
  /** 11 digits, canonical form (01712345678). The only login identifier there
   *  is — see `normalizeBdPhone`. */
  phone: string;
  name: string;
  name_bn: string;
  user_type: UserType;
  email: string;
  /**
   * The institution's **id**, not the record: `UserSerializer` exposes `branch`
   * as a primary key with `branch_name` beside it. `null` means the platform
   * admin, who is not tied to one institution and is the only user allowed to
   * switch between them (`docs/02` §3).
   */
  branch: number | null;
  branch_name: string | null;
  /**
   * The permissions the SERVER resolved for this person: their own list if an
   * admin has ever customised it, otherwise their role's preset — never the
   * two merged (`docs/02` §2.3). Empty means the role preset is being used and
   * the backend did not expand it; `lib/permissions.ts` falls back the same way.
   */
  permissions: string[];
  /** The preset this account sits on, so the permission screen can show what
   *  its boxes would be before an admin customises them. `role` is its id;
   *  `role_name` is the name `ROLE_PRESETS` is keyed by. */
  role: number | null;
  role_name: string | null;
  language: Language;
  photo: string | null;
  is_active: boolean;
  /** True on any account an admin created — the password was said out loud in
   *  order to hand it over, so it must not stay the password. */
  must_change_password?: boolean;
  /**
   * What the SERVER enforces: the explicit list if there is one, otherwise the
   * role's preset. Sent alongside the raw `permissions` so the permission
   * screen can tell "customised" from "still on the preset" — the distinction
   * `docs/02` §2.3 turns on, which a single merged field would hide.
   */
  effective_permissions?: string[];
  last_login?: string | null;
}

/** An institution's study sector (`docs/08` D2). Seeded from
 *  `Branch.institution_type`, then owned and relabelled by the institution. */
export interface Stream {
  id: number;
  code: string;
  name: string;
  /** The institution's OWN Bangla label — a madrasah that writes হাফজ rather
   *  than হিফজ types it here (`docs/08` D2a). */
  name_bn: string;
  order: number;
  is_active: boolean;
}

export interface Session {
  id: number;
  name: string;
  /** Stream ids. The API takes and returns primary keys, not nested rows. */
  streams: number[];
  starts_on: string;
  ends_on: string;
  is_current: boolean;
}

/** A named preset. The matrix is `{resource: [actions]}`; `permissions` is the
 *  same thing flattened, which is what the checkbox screen ticks. */
export interface Role {
  id: number;
  name: string;
  name_bn: string;
  permission_matrix: Record<string, string[]>;
  permissions: string[];
  is_system: boolean;
  is_active: boolean;
  user_count: number;
}

/** One row of the catalogue at `GET /api/accounts/permission-catalog/`. The
 *  permission screen is drawn from these and never from a local copy. */
export interface CatalogResource {
  resource: string;
  label: string;
  label_bn: string;
  actions: string[];
  hint: string;
  hint_bn: string;
}

export interface PermissionCatalog {
  resources: CatalogResource[];
  presets: { name: string; name_bn: string; permissions: string[] }[];
}

/** A row of the live feed (`docs/08` D8). Append-only; `summary` is written at
 *  log time so the feed is one query and stays true after the record changes. */
export interface ActivityRow {
  id: number;
  user: number | null;
  user_label: string;
  branch: number | null;
  branch_name: string | null;
  action: string;
  model: string;
  object_id: string;
  object_label: string;
  summary: string;
  summary_bn: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string;
  user_agent: string;
  created_at: string;
}

/** The cursor poll's response. `last_id` is the MAXIMUM id in the page, not the
 *  last element's — the feed is newest-first, so the last element is oldest. */
export interface ActivityPage {
  items: ActivityRow[];
  last_id: number;
}

/** The `{success, data}` envelope the API puts on non-list responses
 *  (`docs/02` §5). */
interface Envelope<T> {
  success: boolean;
  data: T;
}

export interface LoginResponse {
  access: string;
  refresh: string;
  user: User;
}

/**
 * The one error shape the whole API answers with, from the copied exception
 * handler (`CLAUDE.md` §3.2). `code` is a stable snake_case identifier for us;
 * `message` is the sentence written for the person reading the screen.
 */
export interface ApiErrorBody {
  success: false;
  message: string;
  /** Field-level validation, `{ phone: ["..."] }`. Absent for non-form errors. */
  errors?: Record<string, string[]>;
  code?: string;
}

/** A DRF page. Every list endpoint is paginated (`CLAUDE.md` §5). */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Phase 2 — students, staff, academics ──────────────────────────────────
//
// The shapes below are what the live serializers actually return, read off the
// running API rather than inferred from the models. Two of them are not what a
// reader would guess and are worth stating here:
//
//  - **A student carries no class or section.** `Student` is identity only; the
//    class, the section, the roll and the admission number live on `Enrolment`,
//    one row per session. The "admission history" a screen shows is that list of
//    enrolments — there is no stored history field anywhere.
//  - **Money is a string**, always. `monthly_fee` and the salary fields are
//    Decimals server-side and are never parsed into a JS number here.

export type Gender = 'male' | 'female' | 'other';

export type StudentStatus = 'active' | 'passed_out' | 'withdrawn' | 'transferred';

export type GuardianRelation = 'father' | 'mother' | 'brother' | 'other';

export type AdmissionStatus =
  | 'pending'
  | 'interview'
  | 'accepted'
  | 'rejected'
  | 'admitted'
  | 'cancelled';

export type EmploymentStatus =
  | 'active'
  | 'on_leave'
  | 'suspended'
  | 'resigned'
  | 'terminated'
  | 'transferred';

export type EnrolmentStatus = 'active' | 'promoted' | 'passed' | 'withdrawn' | 'transferred';

export type DocumentOwnerType = 'student' | 'teacher' | 'employee';

/** The guardian as it arrives inlined on a student — the link row, not the
 *  guardian record. Enough to phone somebody without a second request. */
export interface StudentGuardianLink {
  id: number;
  student: number;
  guardian: number;
  guardian_name: string;
  guardian_phone: string;
  relation: GuardianRelation;
  is_primary: boolean;
  created_at: string;
}

export interface Student {
  id: number;
  /** `SIES-000123`. Permanent, never reused, allocated by the server. */
  student_id: string;
  /** The login account, or null — and null is the normal case (`docs/08` D4). */
  user: number | null;
  has_login: boolean;
  stream: number | null;
  stream_name: string | null;
  name: string;
  name_bn: string;
  photo: string | null;
  date_of_birth: string | null;
  gender: Gender | '';
  birth_certificate_no: string;
  nid: string;
  blood_group: string;
  religion_notes: string;
  phone: string;
  email: string;
  // The address is four fields and not one, because the printed admission form
  // has a box for each of them.
  village: string;
  post_office: string;
  upazila: string;
  district: string;
  /** The four joined by the server, for display only. */
  full_address: string;
  present_address: string;
  permanent_address: string;
  previous_institution: string;
  previous_class: string;
  admitted_on: string | null;
  status: StudentStatus;
  status_display: string;
  is_active: boolean;
  guardians: StudentGuardianLink[];
  created_at: string;
  updated_at: string;
}

export interface Guardian {
  id: number;
  name: string;
  name_bn: string;
  relation: GuardianRelation;
  phone: string;
  alt_phone: string;
  nid: string;
  occupation: string;
  monthly_income: string;
  address: string;
  user: number | null;
  is_active: boolean;
  students: { id: number; name: string; student_id: string; is_primary: boolean }[];
}

export interface Admission {
  id: number;
  application_no: string;
  session: number;
  session_name: string;
  stream: number | null;
  stream_name: string | null;
  academic_class: number | null;
  applicant_name: string;
  applicant_name_bn: string;
  dob: string | null;
  gender: Gender | '';
  photo: string | null;
  guardian_name: string;
  guardian_phone: string;
  village: string;
  post_office: string;
  upazila: string;
  district: string;
  address: string;
  previous_institution: string;
  previous_class: string;
  previous_result: string;
  status: AdmissionStatus;
  status_display: string;
  interview_date: string | null;
  interview_score: string | null;
  remarks: string;
  /** Set by the admit endpoint and by nothing else. */
  student: number | null;
  student_name: string | null;
  student_code: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * What one click of Admit produced.
 *
 * Admission is a single transaction that creates the Student, the Enrolment,
 * the guardian link and three numbers. The screen shows all three back, because
 * the numbers are what the office writes on the paper file and there is no
 * second place to look them up from.
 */
export interface AdmitResult {
  student: Student;
  enrolment: number | null;
  admission_number: string | null;
  roll: number | null;
}

export interface StoredDocument {
  id: number;
  owner_type: DocumentOwnerType;
  student: number | null;
  teacher: number | null;
  employee: number | null;
  doc_type: string;
  doc_type_display: string;
  title: string;
  filename: string;
  /** The only way a file leaves the server — the stored path is never exposed,
   *  because these are minors' birth certificates. */
  download_url: string;
  issued_on: string | null;
  expires_on: string | null;
  created_at: string;
}

/** The fields a teacher and an employee both have. */
export interface StaffPerson {
  id: number;
  user: number | null;
  name: string;
  name_bn: string;
  photo: string | null;
  dob: string | null;
  gender: Gender | '';
  nid: string;
  blood_group: string;
  phone: string;
  alt_phone: string;
  email: string;
  village: string;
  post_office: string;
  upazila: string;
  district: string;
  address: string;
  designation: string;
  joining_date: string | null;
  leaving_date: string | null;
  employment_status: EmploymentStatus;
  employment_status_display: string;
  basic_salary: string;
  allowances: string;
  deductions: string;
  gross_salary: string;
  bank_account: string;
  mobile_banking: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TeacherQualification {
  id: number;
  teacher: number;
  degree: string;
  institution: string;
  year: number | null;
  result: string;
  certificate: string | null;
}

export interface Teacher extends StaffPerson {
  teacher_id: string;
  /** Stream ids — which sectors of the institution this teacher works in. */
  streams: number[];
  is_class_teacher: boolean;
  specialization: string;
  max_weekly_periods: number | null;
  qualifications: TeacherQualification[];
}

export interface Employee extends StaffPerson {
  employee_id: string;
  department: string;
  duty_shift: string;
}

export interface AcademicClass {
  id: number;
  stream: number | null;
  session: number;
  name: string;
  name_bn: string;
  /** Mirrored from the session by the model. Read-only. */
  year: number;
  level_order: number;
  capacity: number;
  class_teacher: number | null;
  monthly_fee: string;
  is_active: boolean;
  /** Annotated on the list only — absent from a create or update response. */
  section_count?: number;
}

export interface Section {
  id: number;
  academic_class: number;
  name: string;
  name_bn: string;
  capacity: number;
  room: string;
  in_charge: number | null;
  is_active: boolean;
}

export interface Subject {
  id: number;
  stream: number | null;
  academic_class: number;
  name: string;
  name_bn: string;
  code: string;
  full_marks: number;
  pass_marks: number;
  is_optional: boolean;
  has_practical: boolean;
  practical_marks: number;
  is_active: boolean;
}

/** One row of the bell schedule. Institution-wide, or per stream. */
export interface Period {
  id: number;
  stream: number | null;
  name: string;
  name_bn: string;
  order: number;
  /** `"09:00:00"` — the API returns seconds, an `<input type="time">` does not. */
  start_time: string;
  end_time: string;
  is_break: boolean;
  is_active: boolean;
}

/** 0 = Saturday. Not `Date.getDay()`, which starts on Sunday. */
export type DayOfWeek = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export interface ClassRoutine {
  id: number;
  session: number;
  academic_class: number;
  section: number | null;
  subject: number;
  teacher: number;
  period: number;
  day_of_week: DayOfWeek;
  room: string;
  is_active: boolean;
  teacher_name: string;
  subject_name: string;
  period_name: string;
  /** The names the cell prints, sent with the row rather than looked up: a
   *  teacher's own week spans classes their picker lists never loaded. */
  class_name: string;
  class_name_bn: string;
  section_name: string | null;
  subject_name_bn: string;
  period_name_bn: string;
  period_order: number;
  is_break: boolean;
  start_time: string;
  end_time: string;
  day_display: string;
}

/**
 * A teacher's own week — `GET /class-routines/my-routine/`.
 *
 * A separate endpoint from the filtered list because it answers a different
 * question: the list is scoped to the classes a teacher may reach, this is
 * scoped to the teacher themselves. `?teacher=` is ignored by the server, so
 * there is no id here for a client to change.
 */
export interface MyRoutine {
  session: number | null;
  session_name: string;
  rows: ClassRoutine[];
}

/**
 * A student in a class for a session — and the only place a class, a section, a
 * roll or an admission number is recorded. The list of these for one student IS
 * their admission history.
 */
export interface Enrolment {
  id: number;
  student: number;
  session: number;
  academic_class: number;
  section: number | null;
  roll: number | null;
  admission_number: string;
  status: EnrolmentStatus;
  enrolled_on: string;
  left_on: string | null;
  is_hostel: boolean;
  is_transport: boolean;
  is_active: boolean;
  student_name: string;
  class_name: string;
}

/**
 * Which teacher teaches which subject to which class (`docs/08` D6).
 *
 * Not a label: with `restrict_teachers_to_assigned_classes` on, this row is what
 * makes a class reachable at all — attendance and marks for a class nobody
 * assigned them answer 404.
 */
export interface SubjectAssignment {
  id: number;
  session: number;
  teacher: number;
  subject: number;
  academic_class: number;
  section: number | null;
  is_active: boolean;
  teacher_name: string;
  subject_name: string;
}

// ── Attendance (phase 4) ──────────────────────────────────────────────────

/** `late` counts as present, `half_day` as half — the server's own rule
 *  (`attendance/services.py::_totals`), mirrored in the grid's live totals. */
export type AttendanceStatus =
  | 'present'
  | 'absent'
  | 'late'
  | 'leave'
  | 'holiday'
  | 'half_day';

export type AttendanceSource = 'web' | 'mobile' | 'biometric' | 'import';

/** Why a date or a period cannot be marked. Sent alongside the flag so the
 *  screen never re-derives the rule (`docs/02` §4.4). */
export interface Markability {
  is_markable: boolean;
  /** `future` · `weekly_off` · `window_closed` · … Empty when markable. */
  reason: string;
  reason_text: string;
  reason_text_bn: string;
}

export interface RegisterDay extends Markability {
  /** `2026-03-01`. */
  date: string;
}

export interface RegisterCell {
  status: AttendanceStatus;
  taken_by: number | null;
  taken_by_name: string;
  taken_at: string | null;
  remarks: string;
}

export interface RegisterStudent {
  /** The student's primary key — what `register/bulk/` expects back. */
  student: number;
  /** The printed identifier, `SIES-000123`. Not the key. */
  student_code: string;
  enrolment: number;
  name: string;
  name_bn: string;
  roll: number | null;
  /** Keyed by ISO date. A date with no key was never marked. */
  cells: Record<string, RegisterCell>;
  present: number;
  absent: number;
  late: number;
  leave: number;
  half_day: number;
  holiday: number;
  marked_days: number;
  percent: number | null;
}

export interface MonthRegister {
  month: string;
  class: number;
  section: number | null;
  days: RegisterDay[];
  students: RegisterStudent[];
}

/** One dirty cell. `student` is the primary key, never the printed code. */
export interface RegisterCellInput {
  student: number;
  date: string;
  status: AttendanceStatus;
  remarks?: string;
}

/** A cell the server refused, with its own reason — shown as it came, because
 *  "some cells were not saved" is not something a teacher can act on. */
export interface SkippedCell {
  student: number;
  date: string;
  reason: string;
  reason_text: string;
  reason_text_bn: string;
}

export interface BulkSaveResult {
  saved: number;
  skipped: SkippedCell[];
}

export interface RosterStudent {
  student: number;
  student_code: string;
  enrolment: number;
  name: string;
  name_bn: string;
  roll: number | null;
  status: AttendanceStatus;
  remarks: string;
  taken_by: number | null;
  taken_at: string | null;
  /** False when this row is the defaulted-to-present placeholder rather than
   *  something somebody actually recorded. */
  is_taken: boolean;
}

export interface PeriodRoster extends Markability {
  date: string;
  class: number;
  section: number | null;
  period: number;
  student_count: number;
  students: RosterStudent[];
}

export type PeriodState = 'taken' | 'live' | 'upcoming' | 'missed';

/** One card on the teacher's today board (`docs/08` D7). */
export interface MyDayPeriod extends Markability {
  routine: number;
  class: number;
  class_name: string;
  class_name_bn: string;
  section: number | null;
  section_name: string;
  subject: number | null;
  subject_name: string;
  subject_name_bn: string;
  period: number;
  period_name: string;
  period_name_bn: string;
  period_order: number;
  /** `"08:00"` — minutes, not seconds, unlike `Period.start_time`. */
  start_time: string;
  end_time: string;
  room: string;
  student_count: number;
  state: PeriodState;
}

export interface MyDay {
  date: string;
  periods: MyDayPeriod[];
}

// ── Exams (phase 5) ───────────────────────────────────────────────────────

export type ExamType = 'monthly' | 'half_yearly' | 'annual' | 'test' | 'sabaq' | 'board';

/** Only `publish` moves an exam, and only a principal may call it — the
 *  serializer keeps `status` read-only for exactly that reason. */
export type ExamStatus = 'draft' | 'scheduled' | 'ongoing' | 'marks_entry' | 'published';

export interface Exam {
  id: number;
  session: number;
  session_name: string;
  stream: number | null;
  stream_name: string;
  name: string;
  name_bn: string;
  exam_type: ExamType;
  starts_on: string;
  ends_on: string;
  status: ExamStatus;
  published_by: number | null;
  published_at: string | null;
  created_at: string;
}

export interface ExamClass {
  id: number;
  exam: number;
  academic_class: number;
  class_name: string;
}

export interface ExamSchedule {
  id: number;
  exam: number;
  academic_class: number;
  class_name: string;
  subject: number;
  subject_name: string;
  date: string;
  start_time: string | null;
  end_time: string | null;
  full_marks: string;
  pass_marks: string;
  room: string;
  invigilator: number | null;
}

export interface Mark {
  id: number;
  exam: number;
  student: number;
  student_name: string;
  enrolment: number;
  subject: number;
  subject_name: string;
  obtained: string | null;
  practical_obtained: string | null;
  total: string;
  is_absent: boolean;
  entered_by: number | null;
  entered_at: string | null;
  is_active: boolean;
}

/** One row of the entry grid. Keyed on the **enrolment**, not the student: a
 *  student who repeated a year has two, and only the enrolment says which
 *  year's mark this is. */
export interface MarkRowInput {
  enrolment: number;
  obtained?: string | null;
  practical_obtained?: string | null;
  is_absent?: boolean;
}

export interface MarksSaveResult {
  created: number;
  updated: number;
  unchanged: number;
}

/** The result endpoints assemble plain dicts, so their Decimals arrive as JSON
 *  NUMBERS — unlike the model serializers, which render a Decimal as a string.
 *  Both are accepted here rather than guessed at, and every screen reads them
 *  through `Number()`. */
export interface ResultSubjectLine {
  subject: number;
  subject_name: string;
  subject_name_bn: string;
  full_marks: string | number;
  pass_marks: string | number;
  obtained: string | number | null;
  practical_obtained: string | number | null;
  total: string | number;
  is_absent: boolean;
  is_passed: boolean;
  is_optional?: boolean;
  grade?: string;
  grade_bn?: string;
  /** The subject's grade point; null under the Qawmi method. */
  point?: string | number | null;
}

export interface StudentResult {
  exam: number;
  student: number;
  student_name: string;
  subjects: ResultSubjectLine[];
  total_marks: string | number;
  obtained_marks: string | number;
  percentage: string | number;
  /** null under the Qawmi method, which has no GPA. */
  gpa: string | number | null;
  grade: string;
  grade_bn: string;
  is_passed: boolean;
  failed_subjects: string[];
  is_published: boolean;
  method?: GradingMethod;
  scale_name?: string;
  scale_name_bn?: string;
}

export interface TabulationRow {
  enrolment: number;
  student: number;
  student_name: string;
  roll: number | null;
  /** Keyed by subject id. */
  marks: Record<string, { obtained: string | number | null; practical_obtained: string | number | null; total: string | number; is_absent: boolean; is_passed?: boolean; grade?: string; grade_bn?: string; point?: string | number | null }>;
  total_marks: string | number;
  obtained_marks: string | number;
  percentage: string | number;
  /** null under the Qawmi method, which has no GPA. */
  gpa: string | number | null;
  grade: string;
  grade_bn: string;
  is_passed: boolean;
  failed_subjects: string[];
  rank_in_class: number | null;
  /** Rank among the students of the same section; null outside a section or
   *  for a failed student. */
  rank_in_section: number | null;
  student_name_bn: string;
  /** `SIES-000123`. */
  student_code: string;
  section: number | null;
  section_name: string;
  section_name_bn: string;
}

export interface TabulationSection {
  id: number;
  name: string;
  name_bn: string;
}

export interface Tabulation {
  exam: number;
  academic_class: number;
  /** Marks are not visible to students until this is true (`docs/06` #12). */
  is_published: boolean;
  /** The sections that have students on this sheet, by name. */
  method?: GradingMethod;
  scale_name?: string;
  scale_name_bn?: string;
  sections: TabulationSection[];
  rows: TabulationRow[];
}

/** How a বিভাগ grades — see `exams/grading.py`. */
export type GradingMethod = 'gpa' | 'division';

export interface GradeBand {
  id?: number;
  min_percent: string | number;
  grade: string;
  grade_bn: string;
  point: string | number;
  is_fail: boolean;
}

export interface GradeScale {
  id: number;
  stream: number | null;
  stream_name: string;
  stream_name_bn: string;
  name: string;
  name_bn: string;
  method: GradingMethod;
  optional_bonus_above: string | number;
  is_active: boolean;
  bands: GradeBand[];
  updated_at: string;
}

/** One exam on a student's report: the marksheet plus where they sat it. */
export interface StudentReportExam extends StudentResult {
  exam_name: string;
  exam_name_bn: string;
  exam_type: ExamType;
  status: ExamStatus;
  starts_on: string;
  session: number;
  session_name: string;
  academic_class: number;
  class_name: string;
  class_name_bn: string;
  section: number | null;
  section_name: string;
  section_name_bn: string;
  roll: number | null;
  rank_in_class: number | null;
  rank_in_section: number | null;
  class_size: number;
}

/** Every result one student has, newest exam first. */
export interface StudentReport {
  student: number;
  student_code: string;
  student_name: string;
  student_name_bn: string;
  exams: StudentReportExam[];
}

// ── The printable admission form — `docs/07` ──────────────────────────────
//
// The SERVER renders the form; this dashboard only displays and prints what it
// sends back (`docs/07` §8). Nothing here describes how a block LOOKS — that
// would be a second renderer, and the day the two disagree is the day a printed
// stack of two hundred forms is wrong.

export type FormType = 'admission' | 'undertaking' | 'id_card' | 'certificate';

/** The block types `forms/blocks.py` accepts. Anything else is a 400 on save. */
export type FormBlockType =
  | 'letterhead'
  | 'meta_row'
  | 'prose'
  | 'field_grid'
  | 'question_set'
  | 'bullet_list'
  | 'office_box'
  | 'signature_row'
  | 'spacer'
  | 'divider'
  | 'page_break';

/** `{label, value}` — what a meta row and a field grid are made of. `value`
 *  carries the placeholders; `label` is the printed caption. */
export interface FormLabelledPair {
  label?: string;
  label_bn?: string;
  value?: string;
  width?: string;
}

export interface FormOfficePanel {
  title?: string;
  title_bn?: string;
  lines?: string[];
}

/**
 * One block of a template.
 *
 * A single wide interface rather than a discriminated union because the
 * backend's schema is per-type `(required, optional)` key sets and the editor
 * has to hold a half-edited block that the schema would reject — the union
 * would make "the user has not typed the text yet" a type error.
 */
export interface FormBlock {
  type: FormBlockType;
  text?: string;
  text_bn?: string;
  align?: string;
  indent?: boolean;
  fields?: FormLabelledPair[];
  columns?: number;
  title?: string;
  title_bn?: string;
  section?: string;
  items?: string[];
  style?: string;
  panels?: FormOfficePanel[];
  lines?: string[];
  lines_ar?: string[];
  show_logo?: boolean;
  captions?: string[];
  height?: string;
}

export interface FormTemplate {
  id: number;
  name: string;
  name_bn: string;
  form_type: FormType;
  blocks: FormBlock[];
  paper: 'A4' | 'Legal';
  /** CSS margin shorthand, passed straight to `@page { margin: … }`. */
  margins: string;
  is_default: boolean;
  is_active: boolean;
  /**
   * The closed placeholder set, served WITH the template so the editor's picker
   * is generated from the same table the validator enforces (`docs/07` §4). A
   * local copy would be right until the day somebody adds one to the backend.
   */
  placeholder_groups: Record<string, string[]>;
  created_at: string;
}

export type QuestionType =
  | 'single_choice'
  | 'multi_choice'
  | 'description'
  | 'short_text'
  | 'number'
  | 'date'
  | 'yes_no';

export type QuestionPrintStyle = 'inline' | 'block' | 'checkbox';

export interface QuestionOption {
  value: string;
  label: string;
  label_bn: string;
}

export interface FormQuestion {
  id: number;
  /** Null means reusable across every template of the institution — the common
   *  case, and why the question bank is its own screen. */
  template: number | null;
  section: string;
  text: string;
  text_bn: string;
  type: QuestionType;
  options: QuestionOption[];
  is_required: boolean;
  print_style: QuestionPrintStyle;
  answer_lines: number;
  /** A question that writes a student field stores no answer (`docs/07` §5.2).
   *  Empty string means it stores one. */
  maps_to: string;
  order: number;
  is_active: boolean;
  /** The closed list of bindable student fields, from the server. */
  mappable_fields: string[];
}

/**
 * A form that was printed. `snapshot` is deliberately not in the list shape —
 * it is a whole document, and the reprint endpoint renders it.
 */
export interface PrintedForm {
  id: number;
  admission: number;
  template: number | null;
  form_no: string;
  printed_by: number | null;
  printed_at: string;
  reprint_count: number;
}

// ── Phase 3 — fees and accounts ───────────────────────────────────────────
//
// Read off the running API, not inferred from the models. Four things here are
// not what a reader would guess, and every one of them shapes a screen:
//
//  - **Every amount is a string.** `"1200.00"`, never `1200`. `lib/money.ts`
//    adds them in integer poisha where the API gives no total; nothing here is
//    ever parsed into a JS number for arithmetic.
//  - **`status` and `balance` are derived server-side** and read-only. There is
//    no request body that marks an invoice paid (`docs/06` #8).
//  - **`FeeCategory` does not carry `default_amount`.** The model has the
//    column; the live serializer does not expose it. The field is optional here
//    for that reason, and the setup screen says so rather than editing a value
//    the API will silently drop — see `components/fees/FeeSetupTab.tsx`.
//  - **A fee cannot be filtered by class or by a date range.** `FeeViewSet`'s
//    filterset is `student, category, session, status, period, enrolment,
//    generated_by, is_active` and nothing else, so class and due-date narrowing
//    happen over an enrolment map on the client, exactly as `StudentsTab` does.

export type Recurrence = 'one_time' | 'monthly' | 'session' | 'exam' | 'custom';

/** `docs/06` #8. Derived from `paid_amount` against `payable`, never hand-set. */
export type FeeStatus = 'unpaid' | 'partial' | 'paid' | 'overdue' | 'waived';

/** The eight ways money arrives. The wallets are separate values because
 *  reconciliation is per wallet — a bKash statement and a Nagad statement are
 *  two documents that have to tie out separately. */
export type PaymentMethod =
  | 'cash' | 'bkash' | 'nagad' | 'rocket' | 'bank' | 'cheque' | 'card' | 'online';

/** Deliberately the same eight values as `PaymentMethod`, so the auto-posted
 *  income row carries the receipt's own method unchanged. */
export type LedgerMethod = PaymentMethod;

/** Who wrote a ledger row, and therefore who may change it. Only `manual` is
 *  editable — the API refuses a PATCH on the other two with a 400. */
export type EntrySource = 'manual' | 'fee_payment' | 'payroll';

export type GeneratedBy = 'manual' | 'auto' | 'admission';

/** Which students a fee head is charged to. A small fixed shape, not free-form
 *  JSON: `generate_monthly_fees()` is the only reader and a blob nobody can
 *  enumerate is a filter nobody can debug. Empty `streams` means every stream. */
export interface FeeAppliesTo {
  streams: number[];
  hostel_only: boolean;
  transport_only: boolean;
}

export interface FeeCategory {
  id: number;
  code: string;
  name: string;
  name_bn: string;
  note: string;
  note_bn: string;
  recurrence: Recurrence;
  /** Optional because the live serializer does not send it. See the note above
   *  this block — an invoice cannot be raised for a head with no amount, and
   *  the setup screen has to be able to say so. */
  default_amount?: string | null;
  is_refundable: boolean;
  is_mandatory: boolean;
  applies_to: FeeAppliesTo;
  /** Seeded. A system head is deactivated, never deleted. */
  is_system: boolean;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** One invoice — what a single student owes under one head, once. */
export interface Fee {
  id: number;
  student: number;
  student_name: string;
  /** From the enrolment, so it is blank on an invoice raised before one exists. */
  student_admission_no: string;
  enrolment: number | null;
  category: number;
  category_code: string;
  category_name: string;
  session: number;
  /** `"2026-03"` for a monthly charge, `""` otherwise. Part of the uniqueness
   *  key that makes the monthly job safe to run twice. */
  period: string;
  invoice_no: string;
  amount: string;
  discount: string;
  fine: string;
  /** `amount - discount + fine`, computed and stored server-side. */
  payable: string;
  paid_amount: string;
  /** `payable - paid_amount`. Read-only, and the number the counter works from. */
  balance: string;
  due_date: string;
  status: FeeStatus;
  waived_by: number | null;
  waived_at: string | null;
  waive_reason: string;
  generated_by: GeneratedBy;
  note: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** A receipt. Entirely read-only — written by `collect_fee()` and by nothing
 *  else, and corrected by reversal rather than by an edit. */
export interface Payment {
  id: number;
  fee: number;
  invoice_no: string;
  student: number;
  student_name: string;
  category_name: string;
  receipt_no: string;
  amount: string;
  method: PaymentMethod;
  transaction_id: string;
  paid_at: string;
  collected_by: number | null;
  collected_by_name: string;
  /** The income row this collection posted, written in the same transaction. */
  income: number | null;
  note: string;
  is_reversed: boolean;
  reversed_at: string | null;
  reversed_by: number | null;
  reverse_reason: string;
  created_at: string;
}

export interface CollectFeeBody {
  /** A decimal STRING. Sending a JS number here is how a float gets into the
   *  books; `CollectSerializer` takes a Decimal. */
  amount: string;
  method: PaymentMethod;
  transaction_id?: string;
  /** ISO 8601. Omit for "now", which is the normal case at a counter. */
  paid_at?: string;
  note?: string;
}

export interface CollectResult {
  payment: Payment;
  fee: Fee;
}

/** One row of `GET /api/fees/summary/`. Strings, so nothing becomes a float. */
export interface FeeSummaryRow {
  status: FeeStatus;
  count: number;
  payable: string;
  paid: string;
  balance: string;
}

export interface LedgerCategory {
  id: number;
  code: string;
  name: string;
  name_bn: string;
  note: string;
  note_bn: string;
  is_system: boolean;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** An income head, optionally tied to the fee head that posts into it. */
export interface IncomeCategory extends LedgerCategory {
  fee_category: number | null;
  fee_category_code: string;
}

export type ExpenseCategory = LedgerCategory;

/** The fields Income and Expense share. */
export interface LedgerEntry {
  id: number;
  category: number;
  category_code: string;
  category_name: string;
  voucher_no: string;
  amount: string;
  date: string;
  method: LedgerMethod;
  reference: string;
  description: string;
  attachment: string | null;
  session: number | null;
  /** Read-only. `manual` is the only value this API writes; anything else was
   *  posted by a service and the row refuses to be edited. */
  source: EntrySource;
  recorded_by: number | null;
  recorded_by_name: string;
  is_approved: boolean;
  approved_by: number | null;
  approved_at: string | null;
  is_reversed: boolean;
  reversed_at: string | null;
  reversed_by: number | null;
  reverse_reason: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Income extends LedgerEntry {
  /** The receipt this row was posted from, when `source === 'fee_payment'`. */
  payment: number | null;
  payment_receipt_no: string;
}

export type Expense = LedgerEntry;

export type LedgerPath = '/income/' | '/expenses/';

/** `GET /api/{income,expenses}/summary/` — reversed rows excluded, because a
 *  total that counted them would overstate the month. */
export interface LedgerSummary {
  total: string;
  by_category: {
    category: number | null;
    code: string;
    name: string;
    count: number;
    total: string;
  }[];
}

export class ApiError extends Error {
  status: number;
  /** The stable identifier — `fee_already_paid`, not a sentence. */
  code: string | null;
  errors: Record<string, string[]> | null;

  constructor(status: number, message: string, body?: Partial<ApiErrorBody>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body?.code ?? null;
    this.errors = body?.errors ?? null;
  }
}

// ── Storage keys ──────────────────────────────────────────────────────────
// One place, because a key typed twice is a logout that only happens on
// Tuesdays.
const ACCESS_KEY = 'sies_access_token';
const REFRESH_KEY = 'sies_refresh_token';
const USER_KEY = 'sies_user';
const BRANCH_KEY = 'sies_active_branch';

class ApiClient {
  getBaseUrl(): string {
    return getApiUrl();
  }

  private getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_KEY);
  }

  private getAuthHeaders(): Record<string, string> {
    const token = this.getAccessToken();
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }

  private setTokens(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  }

  private clearTokens(): void {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(BRANCH_KEY);
  }

  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  getStoredUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      // A half-written or older-shaped value must not wedge the app on a blank
      // screen every time it loads.
      localStorage.removeItem(USER_KEY);
      return null;
    }
  }

  // ── Branch selection (platform admin only) ──────────────────────────────
  // `BranchScopeMiddleware` reads `?branch=` and IGNORES it for anyone whose
  // own `user.branch` is set (`docs/02` §3), so sending it always is safe: an
  // institution's own principal cannot widen their scope with a copied URL.

  getActiveBranchId(): number | null {
    const raw = localStorage.getItem(BRANCH_KEY);
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) ? n : null;
  }

  setActiveBranchId(id: number | null): void {
    if (id === null) localStorage.removeItem(BRANCH_KEY);
    else localStorage.setItem(BRANCH_KEY, String(id));
  }

  private withBranch(endpoint: string): string {
    const id = this.getActiveBranchId();
    // A caller that named its own `branch=` means a specific institution — the
    // institution being created, or the one whose streams a platform admin is
    // editing. Appending the switcher's value too would send two, and Django's
    // QueryDict.get answers with the LAST one, so the switcher would silently
    // win over the screen.
    if (id === null || /[?&]branch=/.test(endpoint)) return endpoint;
    return endpoint + (endpoint.includes('?') ? '&' : '?') + `branch=${id}`;
  }

  private async handleResponse<T>(response: Response): Promise<T> {
    if (response.status === 204 || response.headers.get('content-length') === '0') {
      return undefined as T;
    }

    const body: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      const err = (body ?? {}) as Partial<ApiErrorBody>;
      // The backend's handler always fills `message`. The status-line fallback
      // is for the two cases it cannot reach: a proxy error page, and a
      // response that was not JSON at all.
      throw new ApiError(
        response.status,
        err.message || `${response.status} ${response.statusText}`,
        err,
      );
    }

    return body as T;
  }

  // Single-flight lock: with ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION
  // on, concurrent 401s (a data-heavy page fires many calls at once) would each
  // refresh with the SAME old token; the first succeeds and blacklists it, the
  // rest 401 → clearTokens → random logouts. All concurrent callers must share
  // ONE in-flight refresh.
  private refreshPromise: Promise<boolean> | null = null;

  private refreshAccessToken(): Promise<boolean> {
    if (this.refreshPromise) return this.refreshPromise;
    this.refreshPromise = this.doRefresh().finally(() => {
      this.refreshPromise = null;
    });
    return this.refreshPromise;
  }

  private async doRefresh(): Promise<boolean> {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (!refresh) return false;

    try {
      const response = await fetch(`${this.getBaseUrl()}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh }),
      });

      if (response.ok) {
        const data = (await response.json()) as { access: string; refresh?: string };
        localStorage.setItem(ACCESS_KEY, data.access);
        // ROTATE_REFRESH_TOKENS blacklists the one we just sent — keep the new.
        if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh);
        return true;
      }
    } catch {
      // Offline, or the backend is restarting. Falling through clears the
      // tokens, which sends the user to /login — the honest outcome either way.
    }

    this.clearTokens();
    return false;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.getBaseUrl()}${this.withBranch(endpoint)}`;
    const send = () =>
      fetch(url, {
        ...options,
        headers: { ...this.getAuthHeaders(), ...options.headers },
      });

    let response = await send();

    if (response.status === 401 && this.getAccessToken()) {
      if (await this.refreshAccessToken()) response = await send();
    }

    return this.handleResponse<T>(response);
  }

  /** Multipart upload. No Content-Type header — the browser must set the
   *  boundary, and naming the type ourselves strips it. */
  private async upload<T>(
    endpoint: string,
    file: File,
    field = 'file',
    extra?: Record<string, string>,
    // PATCH for a photo replacing one on a row that already exists; POST for a
    // new document. A POST to a detail route is not a route at all.
    method: 'POST' | 'PATCH' = 'POST',
  ): Promise<T> {
    const form = new FormData();
    form.append(field, file);
    for (const [k, v] of Object.entries(extra ?? {})) form.append(k, v);

    const send = () =>
      fetch(`${this.getBaseUrl()}${this.withBranch(endpoint)}`, {
        method,
        headers: { Authorization: `Bearer ${this.getAccessToken()}` },
        body: form,
      });

    let response = await send();
    if (response.status === 401 && this.getAccessToken()) {
      if (await this.refreshAccessToken()) response = await send();
    }
    return this.handleResponse<T>(response);
  }

  /** Escape hatch for callers that need a raw response — a CSV download, a
   *  printable PDF. Same token handling, no JSON parsing. */
  async fetchRaw(endpoint: string, options: RequestInit = {}): Promise<Response> {
    const url = `${this.getBaseUrl()}${this.withBranch(endpoint)}`;
    const send = () =>
      fetch(url, {
        ...options,
        headers: {
          Authorization: `Bearer ${this.getAccessToken()}`,
          ...options.headers,
        },
      });

    let response = await send();
    if (response.status === 401 && this.getAccessToken()) {
      if (await this.refreshAccessToken()) response = await send();
    }
    return response;
  }

  // ── Authentication ──────────────────────────────────────────────────────

  /** Phone + password. There is no other way in: no email login, no OAuth. */
  async login(phone: string, password: string): Promise<LoginResponse> {
    const response = await this.request<LoginResponse>('/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ phone, password }),
    });

    this.setTokens(response.access, response.refresh);
    localStorage.setItem(USER_KEY, JSON.stringify(response.user));
    return response;
  }

  async logout(): Promise<void> {
    const refresh = localStorage.getItem(REFRESH_KEY);
    if (refresh) {
      try {
        await this.request('/auth/logout/', {
          method: 'POST',
          body: JSON.stringify({ refresh }),
        });
      } catch {
        // Blacklisting the token server-side is a courtesy. Failing to do it
        // must never leave somebody logged in on a shared office machine.
      }
    }
    this.clearTokens();
  }

  /** The signed-in user, re-read on boot so a permission change made while
   *  they were away takes effect on their next load rather than their next
   *  login. Returns null when the session is gone. */
  async getCurrentUser(): Promise<User | null> {
    try {
      // `/auth/me/` answers inside the project's `{success, data}` envelope,
      // unlike the login response, which puts the user at the top level.
      const { data: user } = await this.request<Envelope<User>>('/auth/me/');
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      return user;
    } catch {
      return null;
    }
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.request('/auth/change-password/', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  }

  async updateMyLanguage(language: Language): Promise<User> {
    const user = await this.request<User>('/auth/me/', {
      method: 'PATCH',
      body: JSON.stringify({ language }),
    });
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    return user;
  }

  async uploadMyPhoto(file: File): Promise<User> {
    return this.upload<User>('/auth/me/photo/', file, 'photo');
  }

  // ── Branches ────────────────────────────────────────────────────────────

  /** Every institution the caller may see. For a platform admin that is all of
   *  them, which is what the header's branch switcher lists; for anyone else
   *  the backend returns their own and nothing more. */
  async getBranches(): Promise<Branch[]> {
    const page = await this.request<Paginated<Branch>>('/branches/');
    return page.results;
  }

  /** The administrative list — inactive institutions included, paginated, and
   *  filterable. `getBranches()` is the switcher's shorter, active-only view. */
  listBranches(query = ''): Promise<Paginated<Branch>> {
    return this.request<Paginated<Branch>>(`/branches/${query}`);
  }

  /**
   * Create an institution.
   *
   * The backend runs this through `branches.services.create_branch`, which
   * seeds the institution's streams in the same transaction (`docs/08` D1
   * consequence 2). The response is the branch alone, so the caller reads the
   * seeded streams back with `listStreams(branch.id)` to show what was made.
   */
  createBranch(body: Partial<Branch>): Promise<Branch> {
    return this.request<Branch>('/branches/', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  updateBranch(id: number, body: Partial<Branch>): Promise<Branch> {
    return this.request<Branch>(`/branches/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  // ── Streams and sessions ────────────────────────────────────────────────
  // Both are branch-scoped, so `branch` is a REQUEST parameter and never a
  // field in the body: the server stamps it (`CLAUDE.md` §1). A platform admin
  // must name the institution, or the write is a 400 rather than a row in
  // nobody's institution.

  async listStreams(branch: number | null): Promise<Stream[]> {
    const page = await this.request<Paginated<Stream>>(
      `/streams/?ordering=order${branch === null ? '' : `&branch=${branch}`}`,
    );
    return page.results;
  }

  createStream(branch: number, body: Partial<Stream>): Promise<Stream> {
    return this.request<Stream>(`/streams/?branch=${branch}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  updateStream(id: number, branch: number, body: Partial<Stream>): Promise<Stream> {
    return this.request<Stream>(`/streams/${id}/?branch=${branch}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  async listSessions(branch: number | null): Promise<Session[]> {
    const page = await this.request<Paginated<Session>>(
      `/sessions/?ordering=-starts_on${branch === null ? '' : `&branch=${branch}`}`,
    );
    return page.results;
  }

  createSession(branch: number, body: Partial<Session>): Promise<Session> {
    return this.request<Session>(`/sessions/?branch=${branch}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  updateSession(id: number, branch: number, body: Partial<Session>): Promise<Session> {
    return this.request<Session>(`/sessions/${id}/?branch=${branch}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  /**
   * Make this the current session.
   *
   * Written as its own method because it is not a plain field write: at most one
   * session per (branch, stream) may be current, the rule spans the `streams`
   * M2M so no database constraint can hold it, and `SessionViewSet` routes a
   * save that sets the flag through `services.set_current_session` to unset the
   * others. Setting the field from a form beside the rest would leave two
   * sessions current and every default reading the wrong one.
   */
  setCurrentSession(id: number, branch: number): Promise<Session> {
    return this.updateSession(id, branch, { is_current: true });
  }

  // ── Accounts, roles, permissions ────────────────────────────────────────

  listUsers(query = ''): Promise<Paginated<User>> {
    return this.request<Paginated<User>>(`/accounts/users/${query}`);
  }

  /**
   * Create a staff account.
   *
   * `branch` is a request parameter, as everywhere else — except for a platform
   * admin creating another platform admin, who belongs to no institution and
   * for whom `user_type` says so.
   */
  createUser(body: Record<string, unknown>, branch: number | null): Promise<User> {
    return this.request<User>(`/accounts/users/${branch === null ? '' : `?branch=${branch}`}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  updateUser(id: number, body: Record<string, unknown>): Promise<User> {
    return this.request<User>(`/accounts/users/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  /**
   * Replace a person's explicit permission list — the whole list, every time.
   *
   * An empty list is not "no change": it is "put them back on their role's
   * preset" (`docs/02` §2.3), and it is what the reset control on the
   * permission screen sends.
   */
  async setUserPermissions(id: number, permissions: string[]): Promise<User> {
    const { data } = await this.request<Envelope<User>>(
      `/accounts/users/${id}/permissions/`,
      { method: 'POST', body: JSON.stringify({ permissions }) },
    );
    return data;
  }

  async listRoles(): Promise<Role[]> {
    const page = await this.request<Paginated<Role>>('/accounts/roles/?ordering=name');
    return page.results;
  }

  createRole(body: Record<string, unknown>): Promise<Role> {
    return this.request<Role>('/accounts/roles/', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  updateRole(id: number, body: Record<string, unknown>): Promise<Role> {
    return this.request<Role>(`/accounts/roles/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  async getPermissionCatalog(): Promise<PermissionCatalog> {
    const { data } = await this.request<Envelope<PermissionCatalog>>(
      '/accounts/permission-catalog/',
    );
    return data;
  }

  // ── Live activity (`docs/08` D8) ────────────────────────────────────────

  /**
   * One poll of the feed.
   *
   * Cursor, not page number: the table grows while it is being read, and a page
   * number over it returns the same row twice and skips another. `since` is the
   * `last_id` of the previous answer.
   */
  getActivity(params: {
    since?: number | null;
    branch?: number | null;
    user?: number | null;
    action?: string | null;
    limit?: number;
  }): Promise<ActivityPage> {
    const q = new URLSearchParams();
    if (params.since) q.set('since', String(params.since));
    if (params.branch) q.set('branch', String(params.branch));
    if (params.user) q.set('user', String(params.user));
    if (params.action) q.set('action', params.action);
    q.set('limit', String(params.limit ?? 50));
    return this.request<ActivityPage>(`/activity/?${q.toString()}`);
  }

  // ── Phase 2 — students, staff, academics ────────────────────────────────
  //
  // Generic verbs rather than sixty near-identical named methods. Phase 2 alone
  // adds fourteen resources that are all plain DRF routers, and a per-resource
  // wrapper for each would be fourteen copies of `JSON.stringify` hiding the
  // three endpoints below that genuinely are not CRUD — admit, enable-login and
  // the multipart uploads. Those keep their own names, which is the point.
  //
  // `branch` is never passed: `withBranch()` appends the switcher's institution
  // to every request already, and the server ignores it for anyone tied to one.

  list<T>(path: string, query = ''): Promise<Paginated<T>> {
    return this.request<Paginated<T>>(`${path}${query}`);
  }

  /**
   * Every row of a list, followed across pages.
   *
   * For the pickers and lookup maps a screen needs whole — the class list a
   * routine grid is drawn from, the session's enrolments that give each student
   * their class. `page_size` is capped at 200 by the backend, and this stops at
   * `MAX_PAGES` rather than looping forever: a screen that would need more rows
   * than that has outgrown being a picker and should be filtering server-side.
   */
  async listAll<T>(path: string, query = ''): Promise<T[]> {
    const MAX_PAGES = 10;
    const separator = query.includes('?') ? '&' : '?';
    const out: T[] = [];
    for (let page = 1; page <= MAX_PAGES; page++) {
      const chunk = await this.request<Paginated<T>>(
        `${path}${query}${separator}page=${page}&page_size=200`,
      );
      out.push(...chunk.results);
      if (!chunk.next) break;
    }
    return out;
  }

  retrieve<T>(path: string, id: number): Promise<T> {
    return this.request<T>(`${path}${id}/`);
  }

  create<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, { method: 'POST', body: JSON.stringify(body) });
  }

  patch<T>(path: string, id: number, body: Record<string, unknown>): Promise<T> {
    return this.request<T>(`${path}${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  /** Hard delete. Only for rows with no financial or academic history behind
   *  them — a section, a subject, a period, an assignment. Students, enrolments
   *  and admissions have no destroy route at all; they deactivate instead. */
  destroy(path: string, id: number): Promise<void> {
    return this.request<void>(`${path}${id}/`, { method: 'DELETE' });
  }

  /**
   * Turn an application into a student — `docs/02` §4.1.
   *
   * One transaction: the Student, the Enrolment, the guardian, and three
   * allocated numbers. The response carries all three back because the office
   * writes them onto the paper file, and nothing else reports them.
   */
  admit(
    admissionId: number,
    body: {
      academic_class?: number | null;
      section?: number | null;
      roll?: number | null;
      admitted_on?: string | null;
      is_hostel?: boolean;
      is_transport?: boolean;
    },
  ): Promise<AdmitResult> {
    return this.request<AdmitResult>(`/admissions/${admissionId}/admit/`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  /**
   * Give a student a login — `docs/08` D4.
   *
   * An action on the record and never a step in admission: most students have
   * no phone, and requiring one to get a child onto the roll would mean
   * inventing numbers.
   */
  enableStudentLogin(
    studentId: number,
    phone: string,
    password?: string,
  ): Promise<{ user: number; phone: string; must_change_password: boolean }> {
    return this.request(`/students/${studentId}/enable-login/`, {
      method: 'POST',
      body: JSON.stringify(password ? { phone, password } : { phone }),
    });
  }

  /** Attach a guardian, reusing the existing row when the phone already exists
   *  in this institution — which is how siblings share one parent record. */
  addStudentGuardian(
    studentId: number,
    body: { name: string; phone?: string; relation?: string; is_primary?: boolean },
  ): Promise<StudentGuardianLink> {
    return this.request<StudentGuardianLink>(`/students/${studentId}/guardians/`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  /** A photo is a file, so it cannot ride along in the JSON body the rest of
   *  the form is sent as. Saved as a second request once the row exists. */
  uploadPersonPhoto<T>(path: string, id: number, file: File): Promise<T> {
    return this.upload<T>(`${path}${id}/`, file, 'photo', undefined, 'PATCH');
  }

  uploadDocument(
    file: File,
    fields: Record<string, string>,
  ): Promise<StoredDocument> {
    return this.upload<StoredDocument>('/documents/', file, 'file', fields);
  }

  // ── Attendance ──────────────────────────────────────────────────────────
  // Named methods rather than `list()` calls, because none of these four is
  // CRUD: the register is a month of one class in ONE response and the save is
  // a batch — 1,800 cells cannot be 1,800 requests (`docs/02` §5.1).

  getMonthRegister(params: {
    academicClass: number;
    section?: number | null;
    month: string;
  }): Promise<MonthRegister> {
    // The query parameter is `class` — a reserved word in TypeScript, which is
    // why the argument is not called that, and the API's contract, which is why
    // the parameter still is.
    const section = params.section ? `&section=${params.section}` : '';
    return this.request<MonthRegister>(
      `/attendance/register/?class=${params.academicClass}${section}&month=${params.month}`,
    );
  }

  saveMonthRegister(body: {
    academicClass: number;
    section?: number | null;
    month: string;
    cells: RegisterCellInput[];
  }): Promise<BulkSaveResult> {
    return this.request<BulkSaveResult>('/attendance/register/bulk/', {
      method: 'POST',
      body: JSON.stringify({
        class: body.academicClass,
        section: body.section ?? null,
        month: body.month,
        cells: body.cells,
      }),
    });
  }

  getMyRoutine(session?: number | null): Promise<MyRoutine> {
    return this.request<MyRoutine>(
      `/class-routines/my-routine/${session ? `?session=${session}` : ''}`,
    );
  }

  getMyDay(date?: string): Promise<MyDay> {
    return this.request<MyDay>(`/attendance/my-day/${date ? `?date=${date}` : ''}`);
  }

  getPeriodRoster(params: {
    academicClass: number;
    section?: number | null;
    period: number;
    date: string;
  }): Promise<PeriodRoster> {
    const section = params.section ? `&section=${params.section}` : '';
    return this.request<PeriodRoster>(
      `/attendance/class/?class=${params.academicClass}${section}` +
        `&period=${params.period}&date=${params.date}`,
    );
  }

  savePeriodAttendance(body: {
    academicClass: number;
    section?: number | null;
    subject?: number | null;
    period: number;
    date: string;
    cells: RegisterCellInput[];
  }): Promise<BulkSaveResult> {
    return this.request<BulkSaveResult>('/attendance/class/', {
      method: 'POST',
      body: JSON.stringify({
        class: body.academicClass,
        section: body.section ?? null,
        subject: body.subject ?? null,
        period: body.period,
        date: body.date,
        cells: body.cells,
      }),
    });
  }

  // ── Exams ───────────────────────────────────────────────────────────────

  /** One paper's whole grid, in one request and one transaction — the same
   *  shape as the attendance batch, and idempotent for the same reason. */
  saveMarks(examId: number, subject: number, rows: MarkRowInput[]): Promise<MarksSaveResult> {
    return this.request<MarksSaveResult>(`/exams/${examId}/marks/`, {
      method: 'POST',
      body: JSON.stringify({ subject, rows }),
    });
  }

  getTabulation(examId: number, academicClass: number): Promise<Tabulation> {
    return this.request<Tabulation>(
      `/exams/${examId}/tabulation/?academic_class=${academicClass}`,
    );
  }

  getStudentResult(examId: number, student: number): Promise<StudentResult> {
    return this.request<StudentResult>(`/exams/${examId}/result/?student=${student}`);
  }

  /** Every exam this student sat that the caller may see, with ranks. */
  getStudentReport(student: number): Promise<StudentReport> {
    return this.request<StudentReport>(`/exams/student-report/?student=${student}`);
  }

  /** Principal-only, and the moment results become visible to students. There
   *  is no route back: `status` is read-only everywhere else. */
  publishExam(examId: number): Promise<Exam> {
    return this.request<Exam>(`/exams/${examId}/publish/`, { method: 'POST' });
  }

  // ── The printable form — `docs/07` §8 ───────────────────────────────────
  //
  // These three answer with an HTML DOCUMENT rather than JSON, because the page
  // IS the deliverable. `fetchRaw` carries the JWT and the active institution
  // like every other call — a bare `<iframe src>` cannot send an Authorization
  // header, which is why the HTML is fetched and then written into the frame.

  /** An HTML document, or the API's own error turned into an `ApiError` so the
   *  screens handle it exactly like a JSON failure. */
  private async html(endpoint: string): Promise<string> {
    const res = await this.fetchRaw(endpoint, { headers: { Accept: 'text/html' } });
    if (!res.ok) {
      // A failure from this endpoint is still the project's JSON error shape —
      // only the success path is HTML.
      const body = (await res.json().catch(() => null)) as Partial<ApiErrorBody> | null;
      throw new ApiError(
        res.status,
        body?.message || `${res.status} ${res.statusText}`,
        body ?? undefined,
      );
    }
    return res.text();
  }

  /**
   * One applicant's form, print-ready.
   *
   * **`mode: 'filled'` records the print and issues a form number** — that is
   * what `PrintedForm` is for (`docs/07` §6), and it is why the preview fetches
   * once and reuses the result rather than re-fetching on every render.
   */
  admissionFormHtml(
    admissionId: number,
    options: { template?: number | null; mode?: 'filled' | 'blank' } = {},
  ): Promise<string> {
    const query = new URLSearchParams({ mode: options.mode ?? 'filled' });
    if (options.template) query.set('template', String(options.template));
    return this.html(`/admissions/${admissionId}/form/?${query}`);
  }

  /**
   * A template with no applicant behind it — the editor's live A4 preview, and
   * the blank stack a madrasah prints at admission season (`docs/07` §7).
   *
   * A blank comes from HERE rather than from some applicant's `mode=blank`, so
   * printing one needs no application to exist and burns no form number.
   */
  templatePreviewHtml(templateId: number, mode: 'blank' | 'filled' = 'blank'): Promise<string> {
    return this.html(`/form-templates/${templateId}/preview/?mode=${mode}`);
  }

  /** A printed form re-rendered **from its stored snapshot** — what was signed,
   *  not what the record says today (`docs/07` §6). Counts as a reprint. */
  reprintFormHtml(printedFormId: number): Promise<string> {
    return this.html(`/printed-forms/${printedFormId}/reprint/`);
  }

  // ── Phase 3 — fees and accounts ─────────────────────────────────────────
  //
  // The four below are named methods rather than `create()` calls because none
  // of them is CRUD. Each is a service behind one POST (`CLAUDE.md` §4.3), and
  // each answers with something other than the row it wrote.

  /**
   * Take money against one invoice — `docs/06` #10, the most-used endpoint.
   *
   * The response is `{payment, fee}`: the receipt to print, and the invoice
   * with its recomputed balance. The `finance.Income` row is written by the
   * same transaction and is **never** posted by the client — that is the whole
   * property `docs/02` §4.6 buys.
   */
  collectFee(feeId: number, body: CollectFeeBody): Promise<CollectResult> {
    return this.request<CollectResult>(`/fees/${feeId}/collect/`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  /** Write off an invoice's balance. The reason is required by the API and by
   *  the screen — an unexplained waiver is indistinguishable from a theft. */
  waiveFee(feeId: number, reason: string): Promise<Fee> {
    return this.request<Fee>(`/fees/${feeId}/waive/`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  /** Every receipt against one invoice, reversed ones included — a bare array,
   *  not a page. The counter has to be able to explain a balance that moved
   *  back, so a reversed receipt is shown rather than hidden. */
  feePayments(feeId: number): Promise<Payment[]> {
    return this.request<Payment[]>(`/fees/${feeId}/payments/`);
  }

  /** Totals per status over the current filters. **The server is the authority
   *  for these figures** — screens print them rather than adding rows up. */
  feeSummary(query = ''): Promise<FeeSummaryRow[]> {
    return this.request<FeeSummaryRow[]>(`/fees/summary/${query}`);
  }

  /** Un-take money. Never a delete: the receipt stays, marked reversed, and its
   *  income row is reversed in the same transaction. */
  reversePayment(paymentId: number, reason: string): Promise<Payment> {
    return this.request<Payment>(`/payments/${paymentId}/reverse/`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  /** Ledger totals over the current filters, reversed rows excluded. */
  ledgerSummary(path: LedgerPath, query = ''): Promise<LedgerSummary> {
    return this.request<LedgerSummary>(`${path}summary/${query}`);
  }

  /** Reverse a MANUAL income row. An auto-posted one is refused by the API —
   *  reverse its receipt instead, which reverses both. */
  reverseIncome(id: number, reason: string): Promise<Income> {
    return this.request<Income>(`/income/${id}/reverse/`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    });
  }

  /**
   * Attach a scanned voucher to a ledger row.
   *
   * A second request after the row exists, for the same reason a student photo
   * is: a file cannot ride along in the JSON body the rest of the form is sent
   * as, and the row has to exist before there is a URL to PATCH.
   */
  uploadLedgerAttachment<T>(path: LedgerPath, id: number, file: File): Promise<T> {
    return this.upload<T>(`${path}${id}/`, file, 'attachment', undefined, 'PATCH');
  }
}

export const apiClient = new ApiClient();
