import type { Action, Resource } from '../lib/permissions';

/**
 * The navigation model — `docs/02` §6, trimmed to what V1 actually builds.
 *
 * Defined once and read twice: `DashboardLayout` draws the sidebar from it and
 * `App` builds the route table from it. Two copies of this list would drift
 * within a phase, and the failure mode is a sidebar entry that 404s.
 *
 * **Twelve sections, most with sub-items.** A sub-item is not a new screen:
 * it is one of the section's in-page tabs (`lib/useTabParam`), linked as
 * `path?tab=key`. The sidebar and the tab strip are two doors to the same view,
 * so a sub-item can never point somewhere the page does not render. Sections
 * with one view (Staff, My routine, Institutions) have none — a group holding
 * one row is a click that does nothing.
 *
 * An earlier version listed forty rows, most of them V2 features `docs/05`
 * §5.4 defers. That rule still holds: a sub-item is only ever a tab that exists.
 *
 * Deliberately absent, and not to be re-added without a scope decision:
 * Salary · Ledger · Discounts · Notices · Grade scale · attendance reports ·
 * the daily register (the month register covers it) · Enrolment (part of
 * admission) · Documents (a tab on the student record) · the `/reports/*`
 * sub-items · "Add institution" (a button on Institutions, not a menu row).
 *
 * `phase` is which build phase (`docs/05` §8) makes the screen real. Anything
 * above 1 routes to `PhasePlaceholder`, which says so plainly — a link that
 * quietly goes nowhere reads as a broken product rather than an unfinished one.
 */

/** One of a section's in-page tabs, offered in the sidebar. */
export interface NavChild {
  /** The page's `?tab=` value. Must be one the page's `useTabParam` accepts. */
  tab: string;
  /** English source string; the sidebar runs it through `t()`. */
  label: string;
  /** Shown when ANY of these passes; omitted means the parent's gate is
   *  enough. Mirrors the page's own tab gating, so the sidebar never offers a
   *  tab the page would silently swap for another. */
  anyOf?: Array<[Resource, Action]>;
}

export interface NavItem {
  path: string;
  /** English source string; the sidebar runs it through `t()`. */
  label: string;
  icon: string;
  /** The gate. Hidden unless `canView(resource)` passes — the same gate the API
   *  enforces, so a hidden item is one the server would refuse anyway. */
  resource: Resource;
  /** Which build phase makes this screen real. 0–1 = it exists now. */
  phase: number;
  /** Only for a teacher — somebody with a `Teacher` profile behind their
   *  account. A principal's own routine is empty by construction, and a nav row
   *  that always renders "nothing assigned" is a row that teaches people to
   *  ignore the sidebar. */
  teacherOnly?: boolean;
  /** Only for the platform admin — the operator of SIES, whose `user.branch` is
   *  null. An institution's own principal never sees these. */
  platformOnly?: boolean;
  /** The section's tabs, in the page's own order. The first one the reader may
   *  open is the page's default and links to the bare path. */
  children?: NavChild[];
}

/** Overview sits above the rest, on its own. It is the screen nearly everybody
 *  has, and the only one that is nobody's module. */
export const OVERVIEW: NavItem = {
  path: '/',
  label: 'Overview',
  icon: 'overview',
  resource: 'dashboard',
  phase: 0,
};

export const NAV_ITEMS: NavItem[] = [
  // First, and above Students, because for the person who can see it this is
  // the screen they open the system for (docs/08 D7).
  {
    path: '/my-routine',
    label: 'My routine',
    icon: 'clock',
    resource: 'academics',
    phase: 2,
    teacherOnly: true,
  },
  {
    path: '/students',
    label: 'Students',
    icon: 'students',
    resource: 'students',
    phase: 2,
    children: [
      { tab: 'students', label: 'Students', anyOf: [['students', 'view']] },
      { tab: 'admissions', label: 'Admissions', anyOf: [['admissions', 'view']] },
    ],
  },
  {
    path: '/teachers',
    label: 'Teachers',
    icon: 'staff',
    resource: 'teachers',
    phase: 2,
    children: [
      { tab: 'list', label: 'Teachers', anyOf: [['teachers', 'view']] },
      { tab: 'assignments', label: 'Assignments', anyOf: [['academics', 'view']] },
    ],
  },
  { path: '/staff', label: 'Staff', icon: 'employees', resource: 'employees', phase: 2 },
  {
    path: '/academics',
    label: 'Academics',
    icon: 'academics',
    resource: 'academics',
    phase: 2,
    children: [
      { tab: 'classes', label: 'Classes' },
      { tab: 'sections', label: 'Sections' },
      { tab: 'subjects', label: 'Subjects' },
      { tab: 'routine', label: 'Routine' },
    ],
  },
  {
    path: '/attendance',
    label: 'Attendance',
    icon: 'attendance',
    resource: 'attendance',
    phase: 4,
    children: [
      { tab: 'register', label: 'Month register' },
      { tab: 'class', label: 'Class attendance' },
    ],
  },
  {
    path: '/fees',
    label: 'Fees',
    icon: 'fees',
    resource: 'fees',
    phase: 3,
    children: [
      { tab: 'collect', label: 'Collect fee', anyOf: [['fees', 'collect']] },
      { tab: 'invoices', label: 'Invoices' },
      { tab: 'dues', label: 'Dues' },
      { tab: 'setup', label: 'Fee setup', anyOf: [['fees', 'update']] },
    ],
  },
  {
    path: '/accounts',
    label: 'Accounts',
    icon: 'accounts',
    resource: 'finance',
    phase: 3,
    children: [
      { tab: 'income', label: 'Income' },
      { tab: 'expenses', label: 'Expenses' },
    ],
  },
  {
    path: '/exams',
    label: 'Exams',
    icon: 'exams',
    resource: 'exams',
    phase: 5,
    children: [
      { tab: 'exams', label: 'Exams', anyOf: [['exams', 'view']] },
      {
        tab: 'marks',
        label: 'Marks entry',
        anyOf: [['marks', 'enter'], ['marks', 'update'], ['marks', 'view']],
      },
      { tab: 'results', label: 'Results', anyOf: [['exams', 'view']] },
    ],
  },
  {
    path: '/reports',
    label: 'Reports',
    icon: 'reports',
    resource: 'reports',
    phase: 6,
    children: [
      { tab: 'students', label: 'Students' },
      { tab: 'attendance', label: 'Attendance' },
      { tab: 'fees', label: 'Fees' },
      { tab: 'finance', label: 'Accounts' },
      { tab: 'exams', label: 'Exams' },
    ],
  },
  {
    path: '/settings',
    label: 'Settings',
    icon: 'settings',
    resource: 'settings',
    phase: 1,
    children: [
      { tab: 'institution', label: 'Institution' },
      { tab: 'streams', label: 'Streams & Sessions' },
      { tab: 'fee-categories', label: 'Fee categories' },
      { tab: 'form-templates', label: 'Form templates' },
      { tab: 'questions', label: 'Questions' },
    ],
  },
  {
    path: '/users',
    label: 'Users',
    icon: 'users',
    resource: 'users',
    phase: 1,
    children: [
      { tab: 'accounts', label: 'Accounts', anyOf: [['users', 'view']] },
      { tab: 'roles', label: 'Roles', anyOf: [['users', 'view']] },
      { tab: 'activity', label: 'Live activity', anyOf: [['activity', 'view']] },
    ],
  },
  // The operator's own screen. `platformOnly` and not just `branches.view`,
  // because a principal holds `branches.view` for their own institution's
  // settings and must still never meet the list of everybody else's.
  {
    path: '/branches',
    label: 'Institutions',
    icon: 'branches',
    resource: 'branches',
    phase: 1,
    platformOnly: true,
  },
];

/** The last phase whose screens exist.
 *
 *  Six: every V1 screen is built, so `PLACEHOLDER_ITEMS` is empty and nothing
 *  routes to `PhasePlaceholder` any more. The constant stays because the next
 *  feature will arrive the same way — built behind a nav entry before it is
 *  finished — and because `CLAUDE.md` §2a makes a nav row pointing at a
 *  placeholder while its backend is live a bug rather than a pending task.
 *
 *  `phase` on each item stays the phase it was BUILT in, which is still true
 *  afterwards; this is the single edit that turns placeholders into pages. */
export const BUILT_THROUGH_PHASE = 6;

/** Screens finished ahead of their phase's turn.
 *
 *  Empty now. It existed because attendance (4) and exams (5) landed while fees
 *  (3) was still a placeholder, so raising the number alone would have claimed
 *  screens that did not exist yet. Keep the escape hatch; that ordering will
 *  happen again. */
export const BUILT_PATHS: string[] = [];

/** Every item whose module is a later phase, for `App` to turn into placeholder
 *  routes. Permission gating is NOT applied here — a route the user cannot see
 *  in the sidebar still has to resolve if they type it, and a placeholder is a
 *  harmless thing to land on. Real screens gate their own data. */
export const PLACEHOLDER_ITEMS: NavItem[] = NAV_ITEMS.filter(
  (i) => i.phase > BUILT_THROUGH_PHASE && !BUILT_PATHS.includes(i.path),
);

/** Every path the sidebar can reach, for the layout's active-item lookup. */
export const ALL_NAV_PATHS: string[] = [OVERVIEW.path, ...NAV_ITEMS.map((i) => i.path)];
