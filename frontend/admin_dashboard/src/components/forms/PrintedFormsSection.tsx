import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Admission, PrintedForm } from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { formatDhakaDateTime } from '../../lib/timezone';
import { btnSecondary } from '../common/styles';
import FormPreviewModal from './FormPreviewModal';
import type { PreviewRequest } from './FormPreviewModal';

/**
 * Every admission form printed for this student, reprintable (`docs/07` §9).
 *
 * **A reprint comes from the stored snapshot, not from the record.** A student
 * whose name was corrected last year still has a signed form in the office
 * file with the old spelling, and the reprint has to match the paper in that
 * file — otherwise it is a different document wearing the same form number
 * (§6). The distinction is on the screen, not only in the code, because the
 * person clicking Reprint is the person who would otherwise assume it prints
 * today's data.
 *
 * The student's applications are found by filtering the application list on
 * `student`: the admissions endpoint has no `student` filter, so the narrowing
 * happens here. That is the one thing on this screen worth an endpoint.
 */
export default function PrintedFormsSection({ studentId }: { studentId: number }) {
  const { t } = useT();
  const { can } = usePermissions();
  const mayView = can('documents', 'view');

  const [forms, setForms] = useState<PrintedForm[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<PreviewRequest | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!mayView) return;
    setLoading(true);
    try {
      const applications = (
        await apiClient.listAll<Admission>('/admissions/', '?ordering=-created_at')
      ).filter((a) => a.student === studentId);

      const pages = await Promise.all(
        applications.map((a) =>
          apiClient
            .listAll<PrintedForm>('/printed-forms/', `?admission=${a.id}&ordering=-printed_at`)
            .catch(() => [] as PrintedForm[]),
        ),
      );
      setForms(pages.flat());
      setError(null);
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not load the printed forms.')));
    } finally {
      setLoading(false);
    }
  }, [studentId, mayView, t]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  if (!mayView) return null;

  const reprint = (form: PrintedForm) =>
    setPreview({
      // The counter is what makes a second click on the same row a NEW request
      // rather than a cached one, and it is read in an event handler so nothing
      // impure happens during a render.
      key: `reprint-${form.id}-${(seq.current += 1)}`,
      title: `${t('Printed form')} · ${form.form_no}`,
      note: t('This is the form exactly as it was printed and signed — not the record as it stands today.'),
      load: async () => [await apiClient.reprintFormHtml(form.id)],
    });

  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
        {t('Printed forms')}
      </h3>

      {error && (
        <p className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
        {forms.map((form) => (
          <li key={form.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2">
            <span className="min-w-0">
              <span className="block font-mono text-sm font-medium text-gray-900">
                {form.form_no}
              </span>
              <span className="block text-xs text-gray-500">
                {formatDhakaDateTime(form.printed_at)}
                {form.reprint_count > 0 && ` · ${t('Reprints')}: ${form.reprint_count}`}
              </span>
            </span>
            <button type="button" onClick={() => reprint(form)} className={btnSecondary}>
              {t('Reprint from the snapshot')}
            </button>
          </li>
        ))}
        {forms.length === 0 && (
          <li className="px-3 py-4 text-center text-sm text-gray-500">
            {loading ? t('Loading...') : t('No form has been printed for this student yet.')}
          </li>
        )}
      </ul>

      <p className="mt-2 text-xs leading-relaxed text-gray-500">
        {t('A reprint shows what was signed at the time. To print today’s details, use Print form on the application.')}
      </p>

      <FormPreviewModal request={preview} onClose={() => setPreview(null)} />
    </section>
  );
}
