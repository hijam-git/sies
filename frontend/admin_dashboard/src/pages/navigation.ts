import type { Resource } from '../lib/permissions';

/**
 * The navigation model — `docs/02` §6.
 *
 * Defined once and read twice: `DashboardLayout` draws the sidebar from it and
 * `App` builds the route table from it. Two copies of this list would drift
 * within a phase, and the failure mode is a sidebar entry that 404s.
 *
 * `phase` is which build phase (`docs/05` §8) makes the screen real. Anything
 * above 0 routes to `PhasePlaceholder`, which says so plainly — the navigation
 * is complete from the start so the shape of the system is visible, but a link
 * that quietly goes nowhere reads as a broken product rather than an
 * unfinished one.
 *
 * Icons are names into `components/common/NavIcon`.
 */

export interface NavItem {
  path: string;
  /** English source string; the sidebar runs it through `t()`. */
  label: string;
  icon: string;
  /** The gate. Hidden unless `canView(resource)` passes — the same gate the API
   *  enforces, so a hidden item is one the server would refuse anyway. */
  resource: Resource;
  /** Which build phase makes this screen real. 0 = it exists now. */
  phase: number;
  /** Only for the platform admin — the operator of SIES, whose `user.branch` is
   *  null. An institution's own principal never sees these. */
  platformOnly?: boolean;
}

export interface NavGroup {
  label: string;
  icon: string;
  items: NavItem[];
  platformOnly?: boolean;
}

/**
 * `docs/02` §6, in order.
 *
 * One deliberate omission: **Notices → SMS**. §6 lists it, but `docs/08` §7
 * assumption 7 puts SMS in V2 — V1 shows dues and absences on screen only — and
 * `docs/05` §9 is the authority on scope. A nav item for a channel that does
 * not exist is a promise the product cannot keep, so the row is left out rather
 * than shipped as a placeholder that will never fill in.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Academics',
    icon: 'academics',
    items: [
      { path: '/academics/classes', label: 'Classes', icon: 'academics', resource: 'settings', phase: 2 },
      { path: '/academics/sections', label: 'Sections', icon: 'list', resource: 'settings', phase: 2 },
      { path: '/academics/subjects', label: 'Subjects', icon: 'document', resource: 'settings', phase: 2 },
      { path: '/academics/sessions', label: 'Sessions', icon: 'clock', resource: 'settings', phase: 2 },
      { path: '/academics/routine', label: 'Routine', icon: 'clock', resource: 'settings', phase: 2 },
    ],
  },
  {
    label: 'Students',
    icon: 'students',
    items: [
      { path: '/students', label: 'All students', icon: 'students', resource: 'students', phase: 2 },
      { path: '/students/admissions', label: 'Admissions', icon: 'document', resource: 'admissions', phase: 2 },
      { path: '/students/enrolment', label: 'Enrolment', icon: 'list', resource: 'students', phase: 2 },
      { path: '/students/documents', label: 'Documents', icon: 'document', resource: 'documents', phase: 2 },
    ],
  },
  {
    label: 'Staff',
    icon: 'staff',
    items: [
      { path: '/staff/teachers', label: 'Teachers', icon: 'staff', resource: 'teachers', phase: 2 },
      { path: '/staff/employees', label: 'Employees', icon: 'students', resource: 'employees', phase: 2 },
      // D6: an assignment is an access scope, not a note. This screen is what
      // makes a teacher's class list mean anything.
      { path: '/staff/assignments', label: 'Assignments', icon: 'list', resource: 'teachers', phase: 2 },
    ],
  },
  {
    label: 'Attendance',
    icon: 'attendance',
    items: [
      { path: '/attendance/register', label: 'Month register', icon: 'attendance', resource: 'attendance', phase: 4 },
      { path: '/attendance/class', label: 'Class attendance', icon: 'clock', resource: 'attendance', phase: 4 },
      { path: '/attendance/daily', label: 'Daily register', icon: 'list', resource: 'attendance', phase: 4 },
      { path: '/attendance/reports', label: 'Attendance reports', icon: 'reports', resource: 'reports', phase: 4 },
    ],
  },
  {
    label: 'Fees',
    icon: 'fees',
    items: [
      { path: '/fees/structure', label: 'Fee structure', icon: 'list', resource: 'fees', phase: 3 },
      { path: '/fees/invoices', label: 'Invoices', icon: 'document', resource: 'fees', phase: 3 },
      // The screen used more than any other, and the one designed first.
      { path: '/fees/collect', label: 'Collect fee', icon: 'money', resource: 'fees', phase: 3 },
      { path: '/fees/dues', label: 'Dues', icon: 'reports', resource: 'fees', phase: 3 },
      { path: '/fees/discounts', label: 'Discounts', icon: 'fees', resource: 'fees', phase: 3 },
    ],
  },
  {
    label: 'Accounts',
    icon: 'accounts',
    items: [
      { path: '/accounts/income', label: 'Income', icon: 'money', resource: 'finance', phase: 3 },
      { path: '/accounts/expenses', label: 'Expenses', icon: 'money', resource: 'finance', phase: 3 },
      // Its own resource, not `finance`: letting an accountant post the
      // electricity bill is a much smaller decision than letting them see what
      // every teacher earns (`docs/02` §2.1).
      { path: '/accounts/salary', label: 'Salary', icon: 'staff', resource: 'salary', phase: 3 },
      { path: '/accounts/ledger', label: 'Ledger', icon: 'accounts', resource: 'finance', phase: 3 },
    ],
  },
  {
    label: 'Exams',
    icon: 'exams',
    items: [
      { path: '/exams', label: 'Exam list', icon: 'exams', resource: 'exams', phase: 5 },
      { path: '/exams/schedule', label: 'Schedule', icon: 'clock', resource: 'exams', phase: 5 },
      // `marks`, not `exams`: a teacher enters their subject's marks without
      // being able to create an exam or publish a result.
      { path: '/exams/marks', label: 'Marks entry', icon: 'document', resource: 'marks', phase: 5 },
      { path: '/exams/results', label: 'Results', icon: 'reports', resource: 'exams', phase: 5 },
      { path: '/exams/marksheets', label: 'Marksheets', icon: 'document', resource: 'exams', phase: 5 },
    ],
  },
  {
    label: 'Reports',
    icon: 'reports',
    items: [
      { path: '/reports/students', label: 'Student reports', icon: 'students', resource: 'reports', phase: 6 },
      { path: '/reports/fees', label: 'Fee reports', icon: 'fees', resource: 'reports', phase: 6 },
      { path: '/reports/finance', label: 'Finance reports', icon: 'accounts', resource: 'reports', phase: 6 },
      { path: '/reports/exams', label: 'Exam reports', icon: 'exams', resource: 'reports', phase: 6 },
      // The reason the branch model exists — and the operator's view alone.
      { path: '/reports/branches', label: 'Branch comparison', icon: 'branches', resource: 'reports', phase: 6, platformOnly: true },
    ],
  },
  {
    label: 'Notices',
    icon: 'notices',
    items: [
      { path: '/notices', label: 'Notice board', icon: 'notices', resource: 'notices', phase: 6 },
    ],
  },
  {
    label: 'Settings',
    icon: 'settings',
    items: [
      { path: '/settings/institution', label: 'Institution', icon: 'branches', resource: 'settings', phase: 1 },
      { path: '/settings/fee-categories', label: 'Fee categories', icon: 'fees', resource: 'settings', phase: 3 },
      { path: '/settings/grade-scale', label: 'Grade scale', icon: 'exams', resource: 'settings', phase: 5 },
      { path: '/settings/form-templates', label: 'Form templates', icon: 'document', resource: 'settings', phase: 2 },
    ],
  },
  {
    label: 'Users',
    icon: 'users',
    items: [
      { path: '/users', label: 'Accounts & logins', icon: 'users', resource: 'users', phase: 1 },
      { path: '/users/roles', label: 'Roles & permissions', icon: 'settings', resource: 'users', phase: 1 },
      // D8: the operator watches this. `activity.view` is granted to nobody by
      // default, which is why it is its own resource rather than part of users.
      { path: '/users/activity', label: 'Live activity', icon: 'activity', resource: 'activity', phase: 1 },
    ],
  },
  {
    label: 'Branches',
    icon: 'branches',
    platformOnly: true,
    items: [
      { path: '/branches', label: 'All institutions', icon: 'branches', resource: 'branches', phase: 1 },
      { path: '/branches/new', label: 'Add institution', icon: 'settings', resource: 'branches', phase: 1 },
    ],
  },
];

/** Overview sits above the groups, on its own. It is the only screen that
 *  exists in phase 0, and the only one nearly everybody has. */
export const OVERVIEW: NavItem = {
  path: '/',
  label: 'Overview',
  icon: 'overview',
  resource: 'dashboard',
  phase: 0,
};

/** Every item that is not yet built, for `App` to turn into placeholder routes.
 *  Permission gating is NOT applied here — a route the user cannot see in the
 *  sidebar still has to resolve if they type it, and a placeholder is a
 *  harmless thing to land on. Real screens gate their own data. */
export const PLACEHOLDER_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items).filter(
  (i) => i.phase > 0,
);

/** Every path the sidebar can reach, for the layout's active-item lookup. */
export const ALL_NAV_PATHS: string[] = [
  OVERVIEW.path,
  ...NAV_GROUPS.flatMap((g) => g.items.map((i) => i.path)),
];
