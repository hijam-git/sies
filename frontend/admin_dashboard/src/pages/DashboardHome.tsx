import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { Expense, Income } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { formatNumber, formatBDTExact, toBanglaDigits } from '../lib/format';
import { sumMoney } from '../lib/money';
import { currentMonthInDhaka, formatDhakaDate, todayInDhaka } from '../lib/timezone';
import StatCard, { StatIcon } from '../components/common/StatCard';
import CompactActivityFeed from '../components/users/ActivityFeed';

/**
 * The overview.
 *
 * Two halves, and the difference between them is stated on the screen rather
 * than left to be discovered.
 *
 * **Real:** institutions, accounts and current sessions, counted from the phase
 * 1 endpoints, plus the five-row activity feed (`docs/08` D8).
 *
 * **Honestly zero:** students, attendance, fees and staff. The modules that
 * produce those are phases 2 to 4. The cards are drawn now anyway because doing
 * so fixes what the institution's first screen says and what a permission
 * hides, so the later phases fill a shape that has already been agreed — and
 * the note at the foot says why the figures are zero, so nobody reads a working
 * system as a broken one.
 *
 * A teacher signing in gets a different home from phase 4 — their day's classes
 * (`docs/08` D7) — which is why nothing here assumes a whole-institution view.
 */

// Phase 1 replaces this object with the API response. The shape is the
// contract, so writing it down now is what lets the endpoint be built against
// something rather than invented alongside it.
//
// The three fee and finance figures have moved out of it — `useMoneyFigures`
// below reads them from the live phase 3 endpoints. What is left is phases 4
// and 5, and the note at the foot of the page still says so.
const PHASE_0_SUMMARY = {
  present_today: 0,
  attendance_pending_classes: 0,
  marks_pending: 0,
};

/** The three statuses that mean money is owed. `paid` and `waived` are settled. */
const OWING = ['unpaid', 'partial', 'overdue'];

/**
 * The money a principal opens this page for: **collected this month,
 * outstanding, and this month's expenses.**
 *
 * Only one of the three comes back as a single server total, and the reason is
 * worth knowing before reading the numbers:
 *
 *  - **Outstanding** is `GET /api/fees/summary/`, totalled per status in the
 *    database. The three owing rows are added here in integer poisha.
 *  - **Collected this month** and **this month's expenses** have no server-side
 *    date filter to ask for. `LedgerEntryViewSet`'s filterset carries `date` as
 *    an *exact* lookup and nothing else — no `date__gte`, no `from`/`to`. So the
 *    month's rows are read and added here, exactly, in poisha. When a dashboard
 *    summary endpoint exists these collapse into it and the cards do not change.
 */
function useMoneyFigures(enabled: { fees: boolean; finance: boolean }) {
  const [figures, setFigures] = useState<{
    collected: string | null;
    outstanding: string | null;
    expenses: string | null;
  }>({ collected: null, outstanding: null, expenses: null });

  const { fees, finance } = enabled;

  useEffect(() => {
    let alive = true;
    const { year, month } = currentMonthInDhaka();
    const prefix = `${year}-${String(month).padStart(2, '0')}`;
    const inThisMonth = (row: { date: string; is_reversed: boolean }) =>
      row.date.startsWith(prefix) && !row.is_reversed;

    const read = async () => {
      const [summary, income, expenses] = await Promise.all([
        fees ? apiClient.feeSummary('?is_active=true').catch(() => null) : null,
        finance
          ? apiClient
              .listAll<Income>('/income/', '?is_active=true&source=fee_payment&ordering=-date')
              .catch(() => null)
          : null,
        finance
          ? apiClient
              .listAll<Expense>('/expenses/', '?is_active=true&ordering=-date')
              .catch(() => null)
          : null,
      ]);

      if (!alive) return;
      setFigures({
        outstanding: summary
          ? sumMoney(summary.filter((r) => OWING.includes(r.status)).map((r) => r.balance))
          : null,
        collected: income ? sumMoney(income.filter(inThisMonth).map((r) => r.amount)) : null,
        expenses: expenses ? sumMoney(expenses.filter(inThisMonth).map((r) => r.amount)) : null,
      });
    };
    void read();
    return () => {
      alive = false;
    };
  }, [fees, finance]);

  return figures;
}

/**
 * The counts phase 1 can honestly answer.
 *
 * Read as three list requests rather than from a summary endpoint: each is
 * `?page_size`-independent because DRF's `count` is the total before
 * pagination, so asking for page 1 and reading `count` costs one row of
 * transfer and no new backend. When `GET /api/dashboard/summary/` exists these
 * three calls collapse into it and the cards do not change.
 */
function usePhase1Counts(enabled: {
  branches: boolean;
  users: boolean;
  sessions: boolean;
  students: boolean;
  teachers: boolean;
  classes: boolean;
  admissions: boolean;
}) {
  const [counts, setCounts] = useState<{
    branches: number | null;
    users: number | null;
    sessions: number | null;
    students: number | null;
    teachers: number | null;
    classes: number | null;
    pendingAdmissions: number | null;
  }>({
    branches: null,
    users: null,
    sessions: null,
    students: null,
    teachers: null,
    classes: null,
    pendingAdmissions: null,
  });

  const { branches, users, sessions, students, teachers, classes, admissions } = enabled;

  useEffect(() => {
    let alive = true;
    const count = (path: string, query: string, on: boolean) =>
      on
        ? apiClient
            .list<unknown>(path, query)
            .then((p) => p.count)
            .catch(() => null)
        : Promise.resolve(null);

    const read = async () => {
      const [b, u, s, st, te, cl, pa] = await Promise.all([
        branches ? apiClient.listBranches('?page=1').then((p) => p.count).catch(() => null) : null,
        users ? apiClient.listUsers('?page=1&is_active=true').then((p) => p.count).catch(() => null) : null,
        sessions ? apiClient.listSessions(null).then((rows) => rows.filter((x) => x.is_current).length).catch(() => null) : null,
        // `page_size=1` because only `count` is read — a page of 25 rows of
        // student data to render one number is transfer nobody looks at.
        count('/students/', '?page=1&page_size=1&status=active&is_active=true', students),
        count('/teachers/', '?page=1&page_size=1&employment_status=active', teachers),
        count('/classes/', '?page=1&page_size=1&is_active=true', classes),
        count('/admissions/', '?page=1&page_size=1&status=pending', admissions),
      ]);
      if (alive) {
        setCounts({
          branches: b, users: u, sessions: s,
          students: st, teachers: te, classes: cl, pendingAdmissions: pa,
        });
      }
    };
    void read();
    return () => {
      alive = false;
    };
  }, [branches, users, sessions, students, teachers, classes, admissions]);

  return counts;
}

export default function DashboardHome() {
  const { t } = useT();
  const { user } = useAuth();
  const { canView } = usePermissions();

  const s = PHASE_0_SUMMARY;
  // A platform admin with no institution selected is looking across all of
  // them, and "your institution today" would be the wrong sentence.
  const platformWide = user?.branch === null;

  const counts = usePhase1Counts({
    branches: platformWide && canView('branches'),
    users: canView('users'),
    sessions: canView('academics'),
    students: canView('students'),
    teachers: canView('teachers'),
    classes: canView('academics'),
    admissions: canView('admissions'),
  });

  const money = useMoneyFigures({ fees: canView('fees'), finance: canView('finance') });

  const shown = (n: number | null) => (n === null ? '—' : formatNumber(n));
  /** `null` means the request has not landed, or the permission withheld it —
   *  an em dash, never a zero that reads as "nothing was collected". */
  const taka = (v: string | null) => (v === null ? '—' : toBanglaDigits(formatBDTExact(v)));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">
          {t('Assalamu alaikum')}
          {user?.name_bn || user?.name ? `, ${user.name_bn || user.name}` : ''}
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          {platformWide ? t('Here is the platform today.') : t('Here is your institution today.')}
          {' · '}
          {formatDhakaDate(todayInDhaka())}
        </p>
      </header>

      {/* The figures phase 1 can actually answer. Kept above the phase 2–4
          cards so the first thing on the screen is a number that is real. */}
      {(platformWide || canView('users') || canView('academics') || canView('students') || canView('teachers')) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {platformWide && canView('branches') && (
            <StatCard
              tone="blue"
              icon={<StatIcon d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />}
              label={t('Institutions')}
              value={shown(counts.branches)}
              sub={t('On the platform')}
            />
          )}
          {canView('users') && (
            <StatCard
              tone="gray"
              icon={<StatIcon d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />}
              label={t('Accounts')}
              value={shown(counts.users)}
              sub={t('Active logins')}
            />
          )}
          {canView('academics') && (
            <StatCard
              tone="green"
              icon={<StatIcon d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />}
              label={t('Current sessions')}
              value={shown(counts.sessions)}
              sub={t('Academic years running now')}
            />
          )}

          {/* Phase 2's three. Counted the same way — DRF's `count` is the total
              before pagination, so one row of transfer answers each. */}
          {canView('students') && (
            <StatCard
              tone="blue"
              icon={<StatIcon d="M12 14l9-5-9-5-9 5 9 5zm0 0v6m-7-9v5a7 7 0 0014 0v-5" />}
              label={t('Students')}
              value={shown(counts.students)}
              sub={t('On the roll')}
            />
          )}
          {canView('teachers') && (
            <StatCard
              tone="gray"
              icon={<StatIcon d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />}
              label={t('Teachers')}
              value={shown(counts.teachers)}
              sub={t('Currently teaching')}
            />
          )}
          {canView('academics') && (
            <StatCard
              tone="amber"
              icon={<StatIcon d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5" />}
              label={t('Classes')}
              value={shown(counts.classes)}
              sub={t('Across every stream')}
            />
          )}
        </div>
      )}

      {canView('activity') && <CompactActivityFeed />}

      {/* One column at 360px, two from sm, four from xl. Never a fixed width:
          four cards across a phone is four unreadable cards. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {canView('attendance') && (
          <StatCard
            tone="green"
            icon={<StatIcon d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />}
            label={t('Present today')}
            value={formatNumber(s.present_today)}
            sub={
              s.attendance_pending_classes > 0
                ? `${t('Attendance not yet taken')}: ${formatNumber(s.attendance_pending_classes)}`
                : undefined
            }
          />
        )}

        {canView('finance') && (
          <StatCard
            tone="green"
            icon={<StatIcon d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1" />}
            label={t('Collected this month')}
            value={taka(money.collected)}
            sub={t('Fee receipts, posted automatically to income')}
            valueCls="text-emerald-600"
          />
        )}

        {canView('fees') && (
          <StatCard
            tone="red"
            icon={<StatIcon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />}
            label={t('Outstanding dues')}
            value={taka(money.outstanding)}
            sub={t('Owed across every unpaid, part-paid and overdue invoice')}
            valueCls="text-red-600"
          />
        )}

        {canView('finance') && (
          <StatCard
            tone="amber"
            icon={<StatIcon d="M19 14l-7 7m0 0l-7-7m7 7V3" />}
            label={t('Expenses this month')}
            value={taka(money.expenses)}
            sub={t('Entered by hand in Accounts')}
          />
        )}

      </div>

      {/* Work that is WAITING, never a count of things already dealt with — a
          badge that cannot reach zero is wallpaper. Hidden entirely when the
          person can see none of it, rather than shown as an empty heading. */}
      {(canView('admissions') || canView('attendance') || canView('exams')) && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            {t('Waiting for you')}
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {canView('admissions') && (
              <StatCard
                tone="blue"
                icon={<StatIcon d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />}
                label={t('Pending admissions')}
                value={shown(counts.pendingAdmissions)}
              />
            )}
            {canView('attendance') && (
              <StatCard
                tone="red"
                icon={<StatIcon d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />}
                label={t('Unmarked attendance')}
                value={formatNumber(s.attendance_pending_classes)}
              />
            )}
            {canView('exams') && (
              <StatCard
                tone="amber"
                icon={<StatIcon d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />}
                label={t('Marks not entered')}
                value={formatNumber(s.marks_pending)}
              />
            )}
          </div>
        </section>
      )}

      {/* The counts above are real. Attendance, fees and exams are not, and
          saying so is what stops a working screen being read as a broken one.
          Removed as each module lands. */}
      <aside className="rounded-xl border border-blue-100 bg-blue-50 p-4 sm:p-5">
        <p className="text-sm font-medium text-blue-900">
          {t('Attendance and exam figures arrive with their modules.')}
        </p>
        <p className="mt-1 text-sm leading-relaxed text-blue-800">
          {t(
            'Nothing is being hidden — the phases that take attendance and publish results have not been built yet, so those figures are honestly zero. The money figures above are live.',
          )}
        </p>
      </aside>
    </div>
  );
}
