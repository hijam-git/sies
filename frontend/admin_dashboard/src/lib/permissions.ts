/**
 * What a person may do.
 *
 * A role ticks a set of boxes; the boxes are what gets enforced (`docs/02`
 * §2). Fixed roles cannot express "runs admissions but must never see the
 * accounts", and every institution eventually needs exactly that.
 *
 * This file is the dashboard's copy of `accounts/permissions.py`. It decides
 * what is on the SCREEN; the backend decides what actually happens. Where the
 * two disagree the backend wins and the user meets a 403 — so the catalogue
 * below must be kept identical to the one the API serves at
 * `GET /api/accounts/permission-catalog/`.
 */

export type Resource =
  | 'dashboard'
  | 'branches'
  | 'academics'
  | 'students'
  | 'admissions'
  | 'teachers'
  | 'employees'
  | 'attendance'
  | 'fees'
  | 'finance'
  | 'salary'
  | 'exams'
  | 'marks'
  | 'reports'
  | 'notices'
  | 'documents'
  | 'settings'
  | 'users'
  | 'activity';

export type Action =
  | 'view'
  | 'create'
  | 'update'
  | 'delete'
  | 'take'
  | 'collect'
  | 'waive'
  | 'manage'
  | 'publish'
  | 'enter'
  | 'export'
  | 'upload';

/**
 * The catalogue — `docs/02` §2.1. The permission-assignment screen is drawn
 * from this, so a resource missing an action here is an action nobody can be
 * granted however much the backend allows it.
 *
 * Two separations are deliberate:
 *  - `salary` is not `finance`. Letting an accountant post the electricity
 *    bill is a much smaller decision than letting them see what every teacher
 *    earns.
 *  - `marks.enter` is not `exams.publish`. A teacher enters their subject's
 *    marks; only the principal publishes, and publishing is the moment results
 *    become visible to students and the rank is computed.
 */
export const PERMISSION_CATALOG: Record<Resource, readonly Action[]> = {
  dashboard: ['view'],
  branches: ['view', 'create', 'update'],
  // Classes, sections, subjects, sessions, streams and the routine — one
  // resource because they are edited by the same person on the same screens.
  academics: ['view', 'create', 'update', 'delete'],
  students: ['view', 'create', 'update', 'delete'],
  admissions: ['view', 'create', 'update'],
  teachers: ['view', 'create', 'update', 'delete'],
  employees: ['view', 'create', 'update', 'delete'],
  attendance: ['view', 'take', 'update'],
  fees: ['view', 'create', 'update', 'collect', 'waive'],
  finance: ['view', 'create', 'update'],
  salary: ['view', 'manage'],
  exams: ['view', 'create', 'update', 'publish'],
  // `view` is real here, not implied by the other two: the backend catalogue
  // carries it, and a fallback that says "any action implies view" is the kind
  // of rule that later hides a genuine gap.
  marks: ['view', 'enter', 'update'],
  reports: ['view', 'export'],
  notices: ['view', 'create', 'delete'],
  documents: ['view', 'upload', 'delete'],
  settings: ['view', 'update'],
  users: ['view', 'create', 'update'],
  activity: ['view'],
};

export const ALL_RESOURCES = Object.keys(PERMISSION_CATALOG) as Resource[];

/** `{students: ['view','create']}` → `['students.view', 'students.create']`. */
function flatten(matrix: Partial<Record<Resource, readonly Action[]>>): string[] {
  return Object.entries(matrix).flatMap(([resource, actions]) =>
    (actions as readonly Action[]).map((a) => `${resource}.${a}`),
  );
}

/** Every permission there is — what a preset means by "everything". */
export const ALL_PERMISSIONS: string[] = flatten(PERMISSION_CATALOG);

export type RolePreset =
  | 'platform_admin'
  | 'platform_accountant'
  | 'principal'
  | 'accountant'
  | 'admission_officer'
  | 'teacher'
  | 'class_teacher'
  | 'hostel_warden'
  | 'office_assistant'
  | 'general_employee';

const TEACHER_PRESET: string[] = flatten({
  dashboard: ['view'],
  academics: ['view'],
  attendance: ['view', 'take'],
  marks: ['view', 'enter', 'update'],
  students: ['view'],
  exams: ['view'],
});

/**
 * The nine default presets of `docs/02` §2.2, plus the platform accountant.
 *
 * A preset is a starting point, never a cage: any single box can be ticked on
 * any single person, which is the whole point of the model (§2.3).
 */
export const ROLE_PERMISSIONS: Record<RolePreset, readonly string[]> = {
  platform_admin: ALL_PERMISSIONS,

  // Consolidated income and expense across every institution — and nothing
  // else. Reads the money, cannot move it or touch a student record.
  platform_accountant: flatten({
    dashboard: ['view'],
    branches: ['view'],
    finance: ['view'],
    fees: ['view'],
    reports: ['view', 'export'],
  }),

  // Everything in their own institution except opening a new one and reading
  // the platform-wide activity feed — both belong to the operator of SIES.
  principal: ALL_PERMISSIONS.filter(
    (p) => p !== 'branches.create' && p !== 'activity.view',
  ),

  accountant: flatten({
    dashboard: ['view'],
    fees: ['view', 'create', 'update', 'collect', 'waive'],
    finance: ['view', 'create', 'update'],
    reports: ['view', 'export'],
    students: ['view'],
    academics: ['view'],
  }),

  admission_officer: flatten({
    dashboard: ['view'],
    admissions: ['view', 'create', 'update'],
    students: ['view', 'create', 'update'],
    fees: ['view', 'create'],
    documents: ['upload'],
  }),

  teacher: TEACHER_PRESET,

  // A teacher who also owns a class register, so they may correct a cell
  // somebody else filled in.
  class_teacher: [...TEACHER_PRESET, 'attendance.update', 'documents.view'],

  hostel_warden: flatten({
    dashboard: ['view'],
    students: ['view'],
    attendance: ['view', 'take'],
  }),

  office_assistant: flatten({
    dashboard: ['view'],
    students: ['view'],
    documents: ['view', 'upload'],
    notices: ['view'],
  }),

  // Non-teaching staff differ from each other more than teachers do: a warden
  // takes attendance, a librarian does not, a cook needs nothing but their own
  // payslip. One thin preset plus per-person ticks covers all of them without
  // inventing a role per job title.
  general_employee: flatten({ dashboard: ['view'] }),
};

/** Just enough of a user to answer a permission question. */
export interface PermissionSubject {
  permissions?: string[] | null;
  /** The preset's NAME — `"Platform Admin"` — not its id. The API keys its
   *  presets by name, and the ids differ between one deployment and the next. */
  role?: string | null;
}

/** `"Class Teacher"` → `"class_teacher"`. The API names its presets the way an
 *  admin reads them; this file keys them the way code does. */
function presetKey(name: string): RolePreset {
  return name.trim().toLowerCase().replace(/\s+/g, '_') as RolePreset;
}

/**
 * The resolution rule — `docs/02` §2.3, and the one thing in this file that
 * must not be "improved".
 *
 * ```
 * permissions is empty  →  the role preset      ← the normal case
 * permissions is set    →  exactly that list    ← the customised case
 * ```
 *
 * The preset is **never merged** with the custom list. Once an admin has
 * customised a person, that list is the whole truth for them — otherwise
 * unticking a box the preset grants would silently do nothing, which is the
 * most dangerous kind of permission bug. It also means changing a preset moves
 * everyone still on it and leaves customised people alone, which is what an
 * admin expects.
 */
export function effectivePermissions(user: PermissionSubject | null | undefined): string[] {
  if (!user) return [];
  if (user.permissions && user.permissions.length > 0) return user.permissions;
  const preset = user.role ? ROLE_PERMISSIONS[presetKey(user.role)] : undefined;
  return preset ? [...preset] : [];
}

export function can(
  permissions: readonly string[],
  resource: Resource,
  action: Action,
): boolean {
  return permissions.includes(`${resource}.${action}`);
}

/**
 * May they see this at all? The gate on every nav item.
 *
 * `marks` has no `view` — a teacher who may enter marks reaches the screen
 * through `marks.enter` — so "can see it" means "holds any action on it"
 * rather than literally `.view`. Without this the Marks entry item would be
 * invisible to the only role that uses it.
 */
export function canView(permissions: readonly string[], resource: Resource): boolean {
  const actions = PERMISSION_CATALOG[resource];
  if (actions.includes('view')) return can(permissions, resource, 'view');
  return actions.some((a) => can(permissions, resource, a));
}

export function canCreate(permissions: readonly string[], resource: Resource): boolean {
  return can(permissions, resource, 'create');
}

export function canUpdate(permissions: readonly string[], resource: Resource): boolean {
  return can(permissions, resource, 'update');
}

export function canDelete(permissions: readonly string[], resource: Resource): boolean {
  return can(permissions, resource, 'delete');
}

/** The resources a person can reach, for anything that needs the list rather
 *  than a yes/no — the permission screen's summary, an empty-state message. */
export function accessibleResources(permissions: readonly string[]): Resource[] {
  return ALL_RESOURCES.filter((r) => canView(permissions, r));
}
