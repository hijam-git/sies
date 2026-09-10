import type { ActivityRow } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { formatDhakaTime } from '../../lib/timezone';
import { ACTION_LABELS, rowTone, useActivityFeed } from './useActivityFeed';

/**
 * How one activity row reads, and the dashboard's five-row panel.
 *
 * The polling rules live in `useActivityFeed` — this file is only what they
 * look like.
 */

/** One row, in the reader's language, with the tint its action earns. */
export function ActivityLine({ row, compact = false }: { row: ActivityRow; compact?: boolean }) {
  const { t, lang } = useT();
  // `summary` is written at log time rather than rendered now, so the feed is
  // one query with no joins and stays true after the record it describes
  // changes.
  const summary = lang === 'bn' ? row.summary_bn || row.summary : row.summary;

  return (
    <li className={`px-3 py-2 ${rowTone(row)}`}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="font-mono text-xs text-gray-500">{formatDhakaTime(row.created_at)}</span>
        {!compact && row.branch_name && (
          <span className="text-xs font-medium text-gray-600">{row.branch_name}</span>
        )}
        <span className="text-xs text-gray-500">{row.user_label || t('System')}</span>
      </div>
      <p className="mt-0.5 text-sm text-gray-900">
        {summary || t(ACTION_LABELS[row.action] ?? row.action)}
      </p>
      {!compact && row.object_label && <p className="text-xs text-gray-500">{row.object_label}</p>}
    </li>
  );
}

/**
 * The dashboard's five-row version. Same polling rules, no filters and no
 * controls — a glance, not a monitoring board.
 */
export default function CompactActivityFeed() {
  const { t } = useT();
  const { rows, loading, error } = useActivityFeed({}, 5, true);

  return (
    <div className="rounded-xl border border-gray-100 bg-white shadow-sm">
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-900">{t('Live activity')}</h2>
        <span className="flex items-center gap-1.5 text-xs text-gray-500">
          <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden />
          {t('Live')}
        </span>
      </div>
      {loading ? (
        <p className="p-4 text-sm text-gray-500">{t('Loading...')}</p>
      ) : rows.length === 0 ? (
        <p className="p-4 text-sm text-gray-500">
          {error ? t('The feed is not answering right now.') : t('Nothing yet today.')}
        </p>
      ) : (
        <ul className="divide-y divide-gray-50">
          {rows.slice(0, 5).map((row) => (
            <ActivityLine key={row.id} row={row} compact />
          ))}
        </ul>
      )}
    </div>
  );
}
