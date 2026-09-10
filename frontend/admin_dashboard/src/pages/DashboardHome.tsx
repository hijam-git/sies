import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import { formatBDT, formatNumber } from '../lib/format';
import { formatDhakaDate, todayInDhaka } from '../lib/timezone';
import StatCard, { StatIcon } from '../components/common/StatCard';

/**
 * The overview.
 *
 * **Every figure here is zero, and that is the truth rather than a placeholder.**
 * The modules that produce them — enrolment, attendance, fees, payroll — are
 * phases 2 to 4. Phase 1 adds `GET /api/dashboard/summary/`, and this page then
 * reads the numbers from it; the cards, their tones and their gating do not
 * change, only the source.
 *
 * Drawing the cards now rather than an empty page is deliberate: it fixes what
 * the institution's first screen says and what a permission hides, so the later
 * phases fill a shape that has already been agreed. The note at the foot says
 * plainly why the numbers are zero, so nobody reads a working system as a
 * broken one.
 *
 * A teacher signing in gets a different home from phase 4 — their day's classes
 * (`docs/08` D7) — which is why nothing here assumes a whole-institution view.
 */

// Phase 1 replaces this object with the API response. The shape is the
// contract, so writing it down now is what lets the endpoint be built against
// something rather than invented alongside it.
const PHASE_0_SUMMARY = {
  students_enrolled: 0,
  present_today: 0,
  attendance_pending_classes: 0,
  collected_this_month: 0,
  outstanding_dues: 0,
  teachers: 0,
  employees: 0,
  pending_admissions: 0,
  marks_pending: 0,
};

export default function DashboardHome() {
  const { t } = useT();
  const { user } = useAuth();
  const { canView } = usePermissions();

  const s = PHASE_0_SUMMARY;
  // A platform admin with no institution selected is looking across all of
  // them, and "your institution today" would be the wrong sentence.
  const platformWide = user?.branch === null;

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

      {/* One column at 360px, two from sm, four from xl. Never a fixed width:
          four cards across a phone is four unreadable cards. */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {canView('students') && (
          <StatCard
            tone="blue"
            icon={<StatIcon d="M12 14l9-5-9-5-9 5 9 5zm0 0v6m-7-9v5a7 7 0 0014 0v-5" />}
            label={t('Students')}
            value={formatNumber(s.students_enrolled)}
            sub={t('Enrolled this session')}
          />
        )}

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

        {canView('fees') && (
          <StatCard
            tone="amber"
            icon={<StatIcon d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1" />}
            label={t('Collected this month')}
            value={formatBDT(s.collected_this_month)}
            sub={t('Across every fee category')}
            footer={[
              {
                label: t('Outstanding dues'),
                value: formatBDT(s.outstanding_dues),
                cls: s.outstanding_dues > 0 ? 'text-red-600' : 'text-gray-700',
                hint: t('Owed by students still enrolled'),
              },
            ]}
          />
        )}

        {(canView('teachers') || canView('employees')) && (
          <StatCard
            tone="gray"
            icon={<StatIcon d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />}
            label={t('Staff')}
            value={formatNumber(s.teachers + s.employees)}
            sub={t('On the payroll')}
            footer={[
              { label: t('Teachers'), value: formatNumber(s.teachers) },
              { label: t('Employees'), value: formatNumber(s.employees) },
            ]}
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
                value={formatNumber(s.pending_admissions)}
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

      {/* Removed in phase 1, when the numbers above become real. Until then,
          saying nothing would let a working screen be read as a broken one. */}
      <aside className="rounded-xl border border-blue-100 bg-blue-50 p-4 sm:p-5">
        <p className="text-sm font-medium text-blue-900">
          {t('These figures arrive with the modules that produce them.')}
        </p>
        <p className="mt-1 text-sm leading-relaxed text-blue-800">
          {t(
            'Nothing is being hidden — the phases that raise fees, take attendance and admit students have not been built yet, so every figure above is honestly zero.',
          )}
        </p>
      </aside>
    </div>
  );
}
