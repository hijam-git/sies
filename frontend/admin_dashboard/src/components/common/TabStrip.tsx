/**
 * The in-page tab strip.
 *
 * The sidebar carries twelve entries and no sub-items, so a section with
 * several views shows them here instead. A tab strip puts the alternatives
 * beside what you are reading; a nested menu hides them behind a click.
 *
 * **On a phone the strip scrolls sideways inside itself** rather than wrapping
 * into a stack of rows (`CLAUDE.md` §7a rule 1). Four wrapped tabs push the
 * screen's actual content below the fold, and the body must never scroll
 * horizontally — only this container may.
 */

export interface TabDef<T extends string> {
  key: T;
  /** Already translated. */
  label: string;
}

export default function TabStrip<T extends string>({
  tabs,
  active,
  onChange,
  heading,
}: {
  tabs: TabDef<T>[];
  active: T;
  onChange: (tab: T) => void;
  /**
   * The screen's `<h1>`, drawn on the strip's own line from `md` up.
   *
   * It used to sit in a `<header>` above, which cost a 32px line plus 16px of
   * gap on every tabbed screen for one word — and on most of them that word is
   * also the highlighted sidebar row AND the first tab. There is room at the
   * left end of the strip and nothing in it. Below `md` the strip needs its
   * whole width to scroll, so the heading keeps its own line there.
   */
  heading?: string;
}) {
  const strip = (
    <div className="scroll-x" role="tablist">
      {/* w-max so the row keeps its natural width and scrolls, instead of
          compressing every tab until the labels truncate. */}
      <div className="flex w-max min-w-full gap-1">
        {tabs.map((tab) => {
          const selected = tab.key === active;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => onChange(tab.key)}
              className={`min-h-[44px] whitespace-nowrap border-b-2 px-4 text-sm font-medium transition-colors ${
                selected
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-800'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </div>
  );

  if (!heading) return <div className="border-b border-gray-200">{strip}</div>;

  return (
    <div>
      <h1 className="mb-2 text-lg font-bold text-gray-900 md:hidden">{heading}</h1>
      <div className="flex items-stretch gap-4 border-b border-gray-200">
        {/* Two elements, one shown at a time — the same trick FilterBar uses for
            its phone sheet. A single node cannot be both a block above the
            strip and an inline item on it. */}
        {/* A rule after the heading: on several screens the section and its
            first tab are the same word, and without it the title reads as a
            fourth tab. */}
        <h1 className="hidden shrink-0 items-center border-r border-gray-200 pb-2 pr-4 text-lg font-bold text-gray-900 md:flex">
          {heading}
        </h1>
        {strip}
      </div>
    </div>
  );
}
