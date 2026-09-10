import { useState } from 'react';
import { apiClient } from '../../lib/api';
import { useT } from '../../lib/i18n';

/**
 * Downloads whatever the screen is showing as a spreadsheet.
 *
 * Takes the endpoint rather than a "kind", because every module has its own —
 * a fee collection sheet, a defaulter list, a class strength report — and a
 * central list of kinds here would have to be edited from six other modules.
 *
 * The request goes through `apiClient.fetchRaw` so it carries the JWT and the
 * active branch, and refreshes a stale token like every other call. A bare
 * `<a href>` cannot send an Authorization header, which is why this is a
 * button and not a link.
 */
export default function ExportCsvButton({
  endpoint,
  params,
  filename,
  label,
}: {
  /** API path, e.g. `/fees/collections/export/`. */
  endpoint: string;
  /** Usually the period and filters the screen is showing, so the sheet covers
   *  the same rows as the figures beside this button. */
  params?: Record<string, string | undefined>;
  /** Fallback name if the server sends no Content-Disposition. */
  filename?: string;
  label?: string;
}) {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const download = async () => {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      const query = new URLSearchParams(
        Object.entries(params ?? {}).filter(([, v]) => v) as [string, string][],
      ).toString();

      const res = await apiClient.fetchRaw(endpoint + (query ? `?${query}` : ''));
      if (!res.ok) throw new Error(String(res.status));

      const blob = await res.blob();
      const disposition = res.headers.get('Content-Disposition') || '';
      const name = disposition.match(/filename="?([^";]+)"?/)?.[1] || filename || 'export.csv';

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      // Inline rather than an alert(): an alert on a phone covers the screen
      // and has to be dismissed before the user can even see the button again.
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col items-start gap-1">
      <button
        onClick={download}
        disabled={busy}
        className="tap gap-1.5 rounded-lg border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        title={t('Download this list as a spreadsheet')}
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3"
          />
        </svg>
        {busy ? t('Exporting…') : (label ?? t('Export CSV'))}
      </button>
      {failed && (
        <p className="text-xs text-red-600">{t('Could not download the file. Please try again.')}</p>
      )}
    </div>
  );
}
