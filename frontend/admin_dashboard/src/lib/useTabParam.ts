import { useSearchParams } from 'react-router-dom';

/**
 * Keep a page's active tab in the URL (`?tab=dues`).
 *
 * Without this the tab is component state, so a refresh, a bookmark, a shared
 * link or the browser Back button all snap the user back to the first tab —
 * jarring when they were mid-task in another one, and worse here than in most
 * products because these screens are used for hours at a stretch.
 *
 * The default tab is left out of the URL so the plain path stays clean, and an
 * unknown or stale value falls back to it instead of rendering nothing.
 */
export function useTabParam<T extends string>(
  valid: readonly T[],
  fallback: T,
): [T, (tab: T) => void] {
  const [params, setParams] = useSearchParams();
  const raw = params.get('tab') as T | null;
  const tab = raw && (valid as readonly string[]).includes(raw) ? raw : fallback;

  const setTab = (next: T) => {
    const p = new URLSearchParams(params);
    if (next === fallback) p.delete('tab');
    else p.set('tab', next);
    // Not `replace`, so Back returns to the previous tab as users expect.
    setParams(p);
  };

  return [tab, setTab];
}
