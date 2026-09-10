/**
 * The shared control styles.
 *
 * Their own module rather than constants beside `Field`, because a file that
 * exports both components and plain values loses Fast Refresh for everything
 * that imports it — every screen, in this case.
 *
 * `text-base` on inputs is not cosmetic: anything under 16px makes iOS Safari
 * zoom on focus, which throws the whole layout off (`CLAUDE.md` §7a rule 8).
 * `min-h-[44px]` is rule 4 — half these screens are used standing up.
 */

export const inputCls =
  'w-full min-h-[44px] rounded-lg border border-gray-200 bg-white px-3 py-2 text-base ' +
  'text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none ' +
  'focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500';

export const selectCls = inputCls;

export const btnPrimary =
  'tap gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white transition-colors ' +
  'hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50';

export const btnSecondary =
  'tap gap-2 rounded-lg border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 ' +
  'transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50';
