import { useCallback, useMemo, useRef } from 'react';

/**
 * "Is this response still the one being waited for?"
 *
 * Every screen here loads on a filter — an exam, a class, a subject, a month —
 * and every one of those filters can change while a request is in the air. Two
 * requests then race, and the slower one wins simply by landing last: the
 * previous class's marks appear under the current class's heading, and are
 * saved against it. The debounce most `load()`s already have does not prevent
 * this; it only cancels a request that has not started.
 *
 * ```ts
 * const req = useRequestId();
 * const load = useCallback(async () => {
 *   const mine = req.begin();
 *   const rows = await apiClient.listAll(...);
 *   if (!req.isCurrent(mine)) return;   // a newer load has taken over
 *   setRows(rows);
 * }, [req, ...]);
 * ```
 *
 * Guard **every** setter after an await, including `setLoading(false)` and the
 * error branch — a stale failure blanking the screen is the same bug wearing a
 * different hat. The returned object is stable, so it is safe in a dependency
 * list.
 */
export function useRequestId() {
  const latest = useRef(0);

  const begin = useCallback(() => {
    latest.current += 1;
    return latest.current;
  }, []);

  const isCurrent = useCallback((id: number) => id === latest.current, []);

  // Memoised rather than stashed in a second ref: reading a ref during render
  // is exactly what the ref rules forbid, and both callbacks are already stable.
  return useMemo(() => ({ begin, isCurrent }), [begin, isCurrent]);
}

export default useRequestId;
