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
 *
 * **Both of those constraints are about phones, so they are the base classes
 * and only the base classes.** From `sm` up there is a mouse, no zoom-on-focus
 * and a screen with room to show a whole record at once, so the control gets
 * denser: 36px tall, 14px text, tighter padding. Same deliberate split as
 * `filterInputCls` in `FilterBar`.
 */

export const inputCls =
  'w-full min-h-[44px] rounded-lg border border-gray-200 bg-white px-3 py-2 text-base ' +
  'sm:min-h-[36px] sm:px-2.5 sm:py-1 sm:text-sm ' +
  'text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none ' +
  'focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500';

export const selectCls = inputCls;

/* Buttons are small and quiet: 32px from `sm` up, 36px on a phone, 13px text,
   a 6px radius and a hairline shadow. The owner asked for compact buttons
   across the whole panel (2026-09-10), which overrides the earlier 44px rule —
   see `CLAUDE.md` §7a rule 4. The phone keeps 4px more because a thumb is
   less precise than a cursor, and `touch-manipulation` (in `.tap`) removes
   the double-tap delay that makes a small button feel unresponsive. */
const btnBase =
  'tap gap-1.5 rounded-md px-3 text-[13px] font-medium leading-none whitespace-nowrap ' +
  'transition-[background-color,border-color,box-shadow,transform] duration-150 ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 focus-visible:ring-offset-1 ' +
  'active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100';

export const btnPrimary =
  btnBase + ' bg-blue-600 text-white shadow-sm shadow-blue-600/20 hover:bg-blue-700';

export const btnSecondary =
  btnBase + ' border border-gray-200 bg-white text-gray-700 shadow-sm shadow-gray-900/5 ' +
  'hover:border-gray-300 hover:bg-gray-50';

export const btnDanger =
  btnBase + ' border border-red-200 bg-white text-red-700 shadow-sm shadow-gray-900/5 ' +
  'hover:border-red-300 hover:bg-red-50';

/* The same button inside a table row: a notch smaller again (28px from `md`),
   and pulled into the cell's padding so a row with an Edit button is no taller
   than a row without one. Below `md` there is no table — it is a card footer
   button — so it keeps the ordinary phone size. */
export const btnRowAction = btnSecondary + ' md:-my-1 md:min-h-[28px] md:px-2.5 md:text-xs';
