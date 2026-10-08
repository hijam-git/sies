import { useEffect, useState } from 'react';
import { apiClient } from '../lib/api';
import type { Stream } from '../lib/api';
import { useAuth, usePermissions } from '../lib/auth-context';
import { useT } from '../lib/i18n';
import TeachersTab from '../components/staff/TeachersTab';

/**
 * Teachers — the roster.
 *
 * Its own top-level section rather than a tab under a combined "Staff", which
 * is how the data already sees it: `Teacher` and `Employee` are separate models
 * off a shared abstract base (`docs/08` D5), and `docs/02` §2.1 keeps
 * `teachers` and `employees` as separate permission resources so an office
 * manager can maintain the non-teaching roster without ever seeing a teacher's
 * salary. Merging them in the sidebar hid a distinction the rest of the system
 * makes everywhere.
 *
 * There is no Assignments tab any more (`docs/08` D6, 2026-10-08 update). Who
 * teaches what is set on Academics → Routine, and the class teacher on the
 * class form. A second screen saying the same thing only let the two disagree.
 * An old `?tab=assignments` link just opens the roster.
 */
export default function TeachersPage() {
  const { t } = useT();
  const { canView } = usePermissions();
  const { activeBranchId } = useAuth();

  const [streams, setStreams] = useState<Stream[]>([]);

  const maySeeTeachers = canView('teachers');

  useEffect(() => {
    if (maySeeTeachers) {
      void apiClient.listStreams(activeBranchId).then(setStreams).catch(() => setStreams([]));
    }
  }, [activeBranchId, maySeeTeachers]);

  if (!maySeeTeachers) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-bold text-gray-900">{t('Teachers')}</h1>
        <p className="mt-2 text-sm text-gray-500">{t('You do not have permission to do this.')}</p>
      </div>
    );
  }

  return <TeachersTab streams={streams} />;
}
