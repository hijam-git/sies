import { useT } from '../../lib/i18n';

/**
 * The list footer.
 *
 * `PAGE_SIZE` is 25 to match the backend's page-number pagination
 * (`CLAUDE.md` §5) — a client page that is not the server's page produces a
 * footer promising pages the API will not serve.
 *
 * Remember to reset `page` to 1 when a filter changes, or a class of 30
 * filtered down to 4 leaves the user staring at an empty page 2.
 */
export const PAGE_SIZE = 25;

export default function Pagination({
  total,
  page,
  onChange,
  pageSize = PAGE_SIZE,
}: {
  total: number;
  page: number;
  onChange: (p: number) => void;
  pageSize?: number;
}) {
  const { t } = useT();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  // Compact page list: 1 … around-current … last. A madrasah with 900 students
  // has 36 pages, and 36 buttons is a second scrollbar. On a phone the window
  // narrows to the current page alone — 44px targets and five of them do not
  // fit across 360px beside the arrows.
  const build = (window: number): (number | '…')[] => {
    const out: (number | '…')[] = [];
    for (let p = 1; p <= pages; p++) {
      if (p === 1 || p === pages || Math.abs(p - page) <= window) out.push(p);
      else if (out[out.length - 1] !== '…') out.push('…');
    }
    return out;
  };

  const btn =
    'flex h-11 min-w-[44px] items-center justify-center rounded-md border px-3 text-sm';

  const numbers = (nums: (number | '…')[]) =>
    nums.map((n, i) =>
      n === '…' ? (
        <span key={`gap-${i}`} className="px-1 text-gray-400">
          …
        </span>
      ) : (
        <button
          key={n}
          onClick={() => onChange(n)}
          aria-current={n === page ? 'page' : undefined}
          className={`${btn} ${
            n === page
              ? 'border-gray-900 bg-gray-900 text-white'
              : 'border-gray-300 text-gray-600 hover:bg-gray-50'
          }`}
        >
          {n}
        </button>
      ),
    );

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 px-3 py-3 sm:px-4">
      <span className="text-xs text-gray-500">
        {from}–{to} / {total}
      </span>
      <div className="ml-auto flex items-center gap-1">
        <button
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className={`${btn} border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40`}
          aria-label={t('Previous page')}
        >
          ‹
        </button>
        {/* Two windows rather than one responsive class list: Tailwind cannot
            hide a JSX element it never rendered, and the array differs. */}
        <span className="flex items-center gap-1 sm:hidden">{numbers(build(0))}</span>
        <span className="hidden items-center gap-1 sm:flex">{numbers(build(1))}</span>
        <button
          onClick={() => onChange(page + 1)}
          disabled={page >= pages}
          className={`${btn} border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-40`}
          aria-label={t('Next page')}
        >
          ›
        </button>
      </div>
    </div>
  );
}
