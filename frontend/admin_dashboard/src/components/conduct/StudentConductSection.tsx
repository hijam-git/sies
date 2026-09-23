import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { ConductHistoryRow } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { useRequestId } from '../../lib/useRequestId';
import { displayValue } from './shared';

/**
 * This student's observation sheets, newest first — what a class teacher reads
 * before a parents' meeting, and what the counter answers a guardian with.
 *
 * On the student's own record rather than on a screen of its own: the question
 * "how is he doing at নামাজ" is asked about a boy, not about a register, and
 * the answer belongs beside his enrolment history.
 *
 * Silent for anyone without `conduct.view` — the section simply is not there,
 * which is the same gate the API applies. A reader who holds it but whose
 * teacher scope excludes this student gets a 404, and an empty history is the
 * honest thing to show them rather than an error about a boy they cannot see.
 */
export default function StudentConductSection({ studentId }: { studentId: number }) {
  // The server already sends each question's text in Bangla where it has it,
  // so there is nothing for this list to choose between.
  const { t } = useT();
  const { can } = usePermissions();
  const mayView = can('conduct', 'view');

  const [rows, setRows] = useState<ConductHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const req = useRequestId();

  const load = useCallback(async () => {
    if (!mayView) return;
    const mine = req.begin();
    setLoading(true);
    try {
      const history = await apiClient.getStudentConduct(studentId);
      if (!req.isCurrent(mine)) return;
      setRows(history.reports);
    } catch {
      if (!req.isCurrent(mine)) return;
      setRows([]);
    } finally {
      if (req.isCurrent(mine)) setLoading(false);
    }
  }, [studentId, mayView, req]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 100);
    return () => clearTimeout(timer);
  }, [load]);

  if (!mayView) return null;

  return (
    <section>
      <h3 className="mb-0.5 text-xs font-semibold uppercase tracking-wide text-gray-500">
        {t('Conduct')}
      </h3>
      <p className="mb-1.5 text-xs text-gray-500">
        {t('What was observed, newest first — নামাজ, তিলাওয়াত, আদব.')}
      </p>
      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
        {rows.map((row) => (
          <li key={`${row.template}-${row.period}`} className="px-3 py-1.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <span className="text-sm font-medium text-gray-900">{row.period}</span>
              <span className="text-xs text-gray-500">
                {row.template_name}
                {row.filled_by_name && ` · ${row.filled_by_name}`}
              </span>
            </div>
            {/* The answers wrap rather than sitting in columns: the questions
                differ per institution, so there is no fixed set of columns to
                give them, and a sheet is three or four short facts. */}
            <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
              {row.answers.map((answer) => (
                <span key={answer.item} className="text-xs text-gray-600">
                  <span className="text-gray-400">{answer.text}</span>
                  {' '}
                  {displayValue({ type: answer.type }, answer.value, t)}
                </span>
              ))}
            </div>
            {row.remarks && (
              <p className="mt-0.5 text-xs italic text-gray-500">{row.remarks}</p>
            )}
          </li>
        ))}
        {!loading && rows.length === 0 && (
          <li className="px-3 py-3 text-center text-sm text-gray-500">
            {t('Nothing recorded yet.')}
          </li>
        )}
        {loading && (
          <li className="px-3 py-3 text-center text-sm text-gray-400">{t('Loading…')}</li>
        )}
      </ul>
    </section>
  );
}
