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
}: {
  tabs: TabDef<T>[];
  active: T;
  onChange: (tab: T) => void;
}) {
  return (
    <div className="scroll-x border-b border-gray-200" role="tablist">
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
}
