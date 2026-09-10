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
  start_time: string;
  end_time: string;
  day_display: string;
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
}

export const apiClient = new ApiClient();
