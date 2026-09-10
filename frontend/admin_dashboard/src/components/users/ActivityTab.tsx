import { useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { Branch, User } from '../../lib/api';
import { useAuth } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import FilterBar, { filterSelectCls } from '../common/FilterBar';
import { btnSecondary } from '../common/styles';
import { ActivityLine } from './ActivityFeed';
import { ACTION_LABELS, useActivityFeed } from './useActivityFeed';

/**
 * The Live Activity screen (`docs/08` D8).
 *
 * The feed itself is `useActivityFeed`; this is its controls. Pause is the
 * important one and it is deliberately prominent: an owner scanning for a
 * failed login or a permission change is reading a list that would otherwise
 * grow from the top under their eyes every five seconds.
 */
export default function ActivityTab() {
  const { t } = useT();
  const { user: me } = useAuth();

  const [branchFilter, setBranchFilter] = useState('');
  const [userFilter, setUserFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [branches, setBranches] = useState<Branch[]>([]);
  const [people, setPeople] = useState<User[]>([]);

  const isPlatformAdmin = me?.branch === null;

  const filters = useMemo(
    () => ({
      branch: branchFilter ? Number(branchFilter) : null,
      user: userFilter ? Number(userFilter) : null,
      action: actionFilter || null,
    }),
    [branchFilter, userFilter, actionFilter],
  );

  const { rows, pendingCount, paused, setPaused, resume, error, loading } = useActivityFeed(
    filters,
    50,
    true,
  );

  useEffect(() => {
    // Only the operator can filter by institution — for everyone else the
    // backend has already pinned it, and the control would do nothing.
    if (isPlatformAdmin) {
      void apiClient.getBranches().then(setBranches).catch(() => setBranches([]));
    }
    void apiClient
      .listUsers('?page=1&ordering=name')
      .then((page) => setPeople(page.results))
      .catch(() => setPeople([]));
  }, [isPlatformAdmin]);

  const filtering = Boolean(branchFilter || userFilter || actionFilter);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end">
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-sm text-gray-600">
            <span
              className={`h-2.5 w-2.5 rounded-full ${paused ? 'bg-gray-400' : 'bg-emerald-500'}`}
              aria-hidden
            />
            {paused
              ? pendingCount > 0
                ? `${t('Paused')} — ${pendingCount} ${t('new')}`
                : t('Paused')
              : t('Live')}
          </span>
          <button
            type="button"
            onClick={() => (paused ? resume() : setPaused(true))}
            className={`${btnSecondary} px-4`}
          >
            {paused ? t('Resume') : t('Pause')}
          </button>
        </div>
      </div>

      <FilterBar
        active={filtering}
        onClear={() => {
          setBranchFilter('');
          setUserFilter('');
          setActionFilter('');
        }}
      >
        {isPlatformAdmin && (
          <select
            className={filterSelectCls}
            aria-label={t('Institution')}
            value={branchFilter}
            onChange={(e) => setBranchFilter(e.target.value)}
          >
            <option value="">{t('All institutions')}</option>
            {branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name_bn || b.name}
              </option>
            ))}
          </select>
        )}
        <select
          className={filterSelectCls}
          aria-label={t('Person')}
          value={userFilter}
          onChange={(e) => setUserFilter(e.target.value)}
        >
          <option value="">{t('Everyone')}</option>
          {people.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name_bn || p.name}
            </option>
          ))}
        </select>
        <select
          className={filterSelectCls}
          aria-label={t('Action')}
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
        >
          <option value="">{t('All actions')}</option>
          {Object.keys(ACTION_LABELS).map((action) => (
            <option key={action} value={action}>
              {t(ACTION_LABELS[action])}
            </option>
          ))}
        </select>
      </FilterBar>

      {paused && pendingCount > 0 && (
        <button
          type="button"
          onClick={resume}
          className="w-full rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-800"
        >
          {`${pendingCount} ${t('new entries are waiting. Tap to show them.')}`}
        </button>
      )}

      <div className="rounded-xl border border-gray-100 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-center text-sm text-gray-500">{t('Loading...')}</p>
        ) : rows.length === 0 ? (
          <p className="p-6 text-center text-sm text-gray-500">
            {error ? t('The feed is not answering right now.') : t('Nothing yet.')}
          </p>
        ) : (
          <ul className="divide-y divide-gray-50">
            {rows.map((row) => (
              <ActivityLine key={row.id} row={row} />
            ))}
          </ul>
        )}
      </div>

      <p className="text-xs text-gray-400">
        {t('Money entries are tinted; failed logins and permission changes are flagged.')}
      </p>
    </div>
  );
}
