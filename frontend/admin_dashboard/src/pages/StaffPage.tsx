import { usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import EmployeesTab from '../components/staff/EmployeesTab';

/**
 * Staff — the non-teaching roster.
 *
 * Teachers moved to their own section. `Teacher` and `Employee` are separate
 * models off a shared abstract base (`docs/08` D5) and separate permission
 * resources (`docs/02` §2.1), precisely so an office manager can maintain this
 * list without ever seeing a teacher's salary. Keeping them in one sidebar row
 * hid a distinction the rest of the system makes everywhere.
 *
 * One tab, so no tab strip: a strip with a single entry is a control that
 * cannot do anything (`CLAUDE.md` §7b rule 3).
 */
export default function StaffPage() {
  const { t } = useT();
  const { canView } = usePermissions();

  if (!canView('employees')) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Staff')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-bold text-gray-900 sm:text-2xl">{t('Staff')}</h1>
      </header>

      <EmployeesTab />
    </div>
  );
}
