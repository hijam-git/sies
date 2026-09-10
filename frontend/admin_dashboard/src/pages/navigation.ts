import type { Resource } from '../lib/permissions';

/**
 * The navigation model — `docs/02` §6, trimmed to what V1 actually builds.
 *
 * Defined once and read twice: `DashboardLayout` draws the sidebar from it and
 * `App` builds the route table from it. Two copies of this list would drift
 * within a phase, and the failure mode is a sidebar entry that 404s.
 *
 * **Twelve entries, flat — no sub-items.** An earlier version listed forty
 * rows, most of them V2 features `docs/05` §5.4 defers; a sidebar advertising
 * things that will never exist buries the handful of screens that do. Where a
 * section has several views they are in-page tabs (`lib/useTabParam`), which is
 * also the reference project's pattern: a tab strip shows the alternatives
 * beside what you are looking at, a nested menu hides them behind a click.
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
  /** Only for the platform admin — the operator of SIES, whose `user.branch` is
   *  null. An institution's own principal never sees these. */
  platformOnly?: boolean;
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
  { path: '/students', label: 'Students', icon: 'students', resource: 'students', phase: 2 },
  { path: '/staff', label: 'Staff', icon: 'staff', resource: 'teachers', phase: 2 },
  { path: '/academics', label: 'Academics', icon: 'academics', resource: 'academics', phase: 2 },
  { path: '/attendance', label: 'Attendance', icon: 'attendance', resource: 'attendance', phase: 4 },
  { path: '/fees', label: 'Fees', icon: 'fees', resource: 'fees', phase: 3 },
  { path: '/accounts', label: 'Accounts', icon: 'accounts', resource: 'finance', phase: 3 },
  { path: '/exams', label: 'Exams', icon: 'exams', resource: 'exams', phase: 5 },
  { path: '/reports', label: 'Reports', icon: 'reports', resource: 'reports', phase: 6 },
  { path: '/settings', label: 'Settings', icon: 'settings', resource: 'settings', phase: 1 },
  { path: '/users', label: 'Users', icon: 'users', resource: 'users', phase: 1 },
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

/** Every item whose module is a later phase, for `App` to turn into placeholder
 *  routes. Permission gating is NOT applied here — a route the user cannot see
 *  in the sidebar still has to resolve if they type it, and a placeholder is a
 *  harmless thing to land on. Real screens gate their own data. */
export const PLACEHOLDER_ITEMS: NavItem[] = NAV_ITEMS.filter((i) => i.phase > 1);

/** Every path the sidebar can reach, for the layout's active-item lookup. */
export const ALL_NAV_PATHS: string[] = [OVERVIEW.path, ...NAV_ITEMS.map((i) => i.path)];
