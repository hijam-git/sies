import { useEffect, useRef, useState } from 'react';
import { apiClient } from '../../lib/api';
import type { ActivityRow } from '../../lib/api';

/**
 * The live activity feed's polling (`docs/08` D8).
 *
 * **A cursor poll every five seconds, not a WebSocket.** A five-second delay is
 * invisible to somebody reading a list of events, and Channels would add an
 * ASGI server, a channel layer and a second deployment shape for an audience of
 * a handful of platform admins watching a board.
 *
 * Cursor and not page number because the table grows while it is being read: a
 * page number over it returns one row twice and skips another. `since` is the
 * previous answer's `last_id`, which is the MAXIMUM id in that page — the feed
 * is newest-first, so its last element is the oldest and handing that back
 * would replay the same page forever.
 *
 * Three behaviours, all for one reason — the list must never move under the
 * reader's cursor:
 *
 *  - a Pause button;
 *  - polling stops while the tab is hidden;
 *  - what arrives during a pause is counted and held, so the header can say
 *    "paused — N new" instead of quietly reordering what is on screen.
 *
 * Separated from the rendering so the dashboard's five-row panel and the full
 * screen share one implementation of those rules rather than two that drift.
 */

/** `docs/08` D8's action vocabulary. */
const MONEY_ACTIONS = new Set(['collect', 'waive', 'income', 'expense', 'reverse']);
const ALERT_ACTIONS = new Set(['login_failed', 'permission_changed', 'role_changed']);

export const ACTION_LABELS: Record<string, string> = {
  create: 'Created',
  update: 'Updated',
  delete: 'Deleted',
  login: 'Login',
  login_failed: 'Failed login',
  collect: 'Fee collected',
  waive: 'Fee waived',
  publish: 'Results published',
  take_attendance: 'Attendance taken',
  permission_changed: 'Permission changed',
  role_changed: 'Role changed',
};

/** Money is tinted; the two an owner actually watches for are flagged red. */
export function rowTone(row: ActivityRow): string {
  if (ALERT_ACTIONS.has(row.action)) return 'border-l-4 border-red-400 bg-red-50';
  if (MONEY_ACTIONS.has(row.action)) return 'border-l-4 border-amber-300 bg-amber-50';
  return 'border-l-4 border-transparent';
}

export interface FeedFilters {
  branch?: number | null;
  user?: number | null;
  action?: string | null;
}

export function useActivityFeed(filters: FeedFilters, limit: number, enabled: boolean) {
  const [rows, setRows] = useState<ActivityRow[]>([]);
  const [pending, setPending] = useState<ActivityRow[]>([]);
  const [paused, setPaused] = useState(false);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const key = `${filters.branch ?? ''}|${filters.user ?? ''}|${filters.action ?? ''}`;

  // A filter change is a different feed. Adjusted during render rather than in
  // an effect: an effect would paint the previous institution's rows under the
  // new filter for a frame first, and React re-runs this render immediately
  // without ever showing the discarded output.
  const [lastKey, setLastKey] = useState(key);
  const [epoch, setEpoch] = useState(0);
  if (lastKey !== key) {
    setLastKey(key);
    setEpoch((e) => e + 1);
    setRows([]);
    setPending([]);
    setLoading(true);
  }

  // The cursor is a ref, not state: the poll must read the newest value without
  // the interval being torn down and rebuilt on every tick. It carries its
  // epoch so a filter change resets it INSIDE the poll — writing a ref during
  // render is what the rule about refs exists to stop.
  const cursor = useRef({ epoch: 0, id: 0 });

  const branch = filters.branch ?? null;
  const person = filters.user ?? null;
  const action = filters.action ?? null;

  useEffect(() => {
    if (!enabled) return;
    let alive = true;

    // Defined inside the effect: state set from an async continuation is fine,
    // but a callback declared outside and called in the effect body reads as a
    // synchronous update and cascades a render.
    const poll = async () => {
      if (cursor.current.epoch !== epoch) cursor.current = { epoch, id: 0 };

      try {
        const page = await apiClient.getActivity({
          since: cursor.current.id || null,
          branch,
          user: person,
          action,
          limit,
        });
        if (!alive) return;
        setError(false);
        if (page.last_id > cursor.current.id) cursor.current = { epoch, id: page.last_id };
        if (page.items.length === 0) return;

        // Trimmed to four pages: a board left open overnight must not grow into
        // a list the browser cannot scroll.
        if (paused) setPending((held) => [...page.items, ...held]);
        else setRows((current) => [...page.items, ...current].slice(0, limit * 4));
      } catch {
        // A failed poll is not a failed screen: the next tick is five seconds
        // away, and blanking the feed because one request timed out would lose
        // what the reader was looking at.
        if (alive) setError(true);
      } finally {
        if (alive) setLoading(false);
      }
    };

    void poll();

    const tick = () => {
      // Nobody is reading a hidden tab, and the browser throttles its timers
      // anyway — so this skips rather than queueing a burst of catch-up
      // requests for the moment it comes back.
      if (!document.hidden) void poll();
    };

    const id = window.setInterval(tick, 5000);
    // …and one immediate poll when it does come back, so the feed is current by
    // the time the reader has finished looking at it.
    const onVisible = () => {
      if (!document.hidden) void poll();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      alive = false;
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [enabled, epoch, branch, person, action, limit, paused]);

  /** Release what was held, in one deliberate move by the reader. */
  const resume = () => {
    setRows((current) => [...pending, ...current].slice(0, limit * 4));
    setPending([]);
    setPaused(false);
  };

  return { rows, pendingCount: pending.length, paused, setPaused, resume, error, loading };
}
