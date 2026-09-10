/**
 * A table header that sorts.
 *
 * One click sorts ascending, a second reverses it, a third clears it and gives
 * the server's own order back. The arrow only appears on the active column, so
 * the header row stays quiet until it is used.
 *
 * Table-only by nature — below `md`, `ResponsiveTable` draws cards and there is
 * no header row to click. A screen that needs sorting on a phone puts it in the
 * FilterBar as a select instead.
 */
export interface SortState<K extends string> {
  key: K;
  dir: 'asc' | 'desc';
}

export default function SortableTh<K extends string>({
  label,
  sortKey,
  sort,
  onSort,
  className = '',
  cellClass = 'px-4 py-3 text-left',
}: {
  label: string;
  sortKey: K;
  sort: SortState<K> | null;
  onSort: (key: K) => void;
  className?: string;
  /** Padding and alignment. Written out in full (never built from a variable)
   *  because Tailwind only ships the classes it can see in the source. */
  cellClass?: string;
}) {
  const active = sort?.key === sortKey;
  return (
    <th
      className={`${cellClass} text-xs font-medium uppercase tracking-wide text-gray-500 ${className}`}
      aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={`group inline-flex min-h-[32px] items-center gap-1 uppercase hover:text-gray-900 ${
          active ? 'text-gray-900' : ''
        }`}
      >
        {label}
        <span
          className={`text-[10px] leading-none ${
            active ? 'opacity-100' : 'opacity-0 group-hover:opacity-40'
          }`}
        >
          {active && sort.dir === 'desc' ? '▼' : '▲'}
        </span>
      </button>
    </th>
  );
}
