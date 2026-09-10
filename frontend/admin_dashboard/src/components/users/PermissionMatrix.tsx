import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { CatalogResource, PermissionCatalog } from '../../lib/api';
import { useT } from '../../lib/i18n';

/**
 * The permission screen (`docs/02` §2.3).
 *
 * Drawn entirely from `GET /api/accounts/permission-catalog/` — its labels, its
 * hints, its action lists. Never from a copy in this file: the backend is what
 * enforces these, and a second list here would agree with it right up until the
 * day somebody adds an action to one of them.
 *
 * **The semantics are the hard part, not the checkboxes.** A preset is a
 * starting point; the moment an admin customises a person, the explicit list is
 * the whole truth for them and is NOT merged with the preset. So the UI says so
 * in words, shows which state this person is in, and offers an explicit way
 * back to the preset — which is an empty list, not a re-tick of every box.
 *
 * **Layout.** A resource × action grid is wide by nature. Below `md` it is an
 * accordion, one resource per row, its actions stacked inside — not a table
 * behind a horizontal scrollbar, which on a phone hides the very column the
 * reader is looking for (`CLAUDE.md` §7a).
 */

const ACTION_LABELS: Record<string, string> = {
  view: 'View',
  create: 'Create',
  update: 'Edit',
  delete: 'Delete',
  take: 'Take',
  collect: 'Collect',
  waive: 'Waive',
  manage: 'Manage',
  publish: 'Publish',
  enter: 'Enter',
  export: 'Export',
  upload: 'Upload',
};

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

function ResourceRow({
  resource,
  selected,
  onToggle,
  onToggleAll,
  readOnly,
  bn,
}: {
  resource: CatalogResource;
  selected: Set<string>;
  onToggle: (permission: string) => void;
  onToggleAll: (resource: CatalogResource, on: boolean) => void;
  readOnly: boolean;
  bn: boolean;
}) {
  const { t } = useT();
  const granted = resource.actions.filter((a) => selected.has(`${resource.resource}.${a}`));
  const allOn = granted.length === resource.actions.length;
  const [open, setOpen] = useState(false);

  const checkbox = (action: string) => {
    const permission = `${resource.resource}.${action}`;
    return (
      <label
        key={action}
        className={`flex min-h-[44px] items-center gap-2 rounded-lg px-2 ${
          readOnly ? 'cursor-default' : 'cursor-pointer hover:bg-gray-50'
        }`}
      >
        <input
          type="checkbox"
          className="h-5 w-5 shrink-0 rounded border-gray-300 text-blue-600 disabled:opacity-60"
          checked={selected.has(permission)}
          disabled={readOnly}
          onChange={() => onToggle(permission)}
        />
        <span className="text-sm text-gray-800">{t(actionLabel(action))}</span>
      </label>
    );
  };

  return (
    <div className="border-b border-gray-100 last:border-0">
      {/* ── Phone: an accordion row ───────────────────────────────────── */}
      <div className="md:hidden">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex min-h-[52px] w-full items-center gap-3 px-3 text-left"
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-gray-900">
              {bn ? resource.label_bn || resource.label : resource.label}
            </span>
            <span className="block text-xs text-gray-500">
              {granted.length}/{resource.actions.length} {t('granted')}
            </span>
          </span>
          <span className="text-gray-400">{open ? '−' : '+'}</span>
        </button>

        {open && (
          <div className="px-3 pb-3">
            <p className="mb-2 text-xs leading-relaxed text-gray-500">
              {bn ? resource.hint_bn || resource.hint : resource.hint}
            </p>
            <div className="grid grid-cols-2 gap-1">
              {resource.actions.map(checkbox)}
            </div>
            {!readOnly && (
              <button
                type="button"
                onClick={() => onToggleAll(resource, !allOn)}
                className="tap mt-1 rounded-lg px-2 text-xs font-medium text-blue-700"
              >
                {allOn ? t('Clear all') : t('Select all')}
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── md and up: label, hint, actions in a row ──────────────────── */}
      <div className="hidden gap-4 p-3 md:flex">
        <div className="w-56 shrink-0">
          <p className="text-sm font-medium text-gray-900">
            {bn ? resource.label_bn || resource.label : resource.label}
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-gray-500">
            {bn ? resource.hint_bn || resource.hint : resource.hint}
          </p>
          {!readOnly && (
            <button
              type="button"
              onClick={() => onToggleAll(resource, !allOn)}
              className="mt-1 text-xs font-medium text-blue-700 hover:underline"
            >
              {allOn ? t('Clear all') : t('Select all')}
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1">{resource.actions.map(checkbox)}</div>
      </div>
    </div>
  );
}

export default function PermissionMatrix({
  catalog,
  selected,
  onChange,
  readOnly = false,
  /** Shown above the grid. The role screen and the per-person screen mean
   *  different things by the same boxes, and each says which. */
  header,
}: {
  catalog: PermissionCatalog;
  selected: string[];
  onChange: (next: string[]) => void;
  readOnly?: boolean;
  header?: ReactNode;
}) {
  const { lang } = useT();
  const set = useMemo(() => new Set(selected), [selected]);

  const toggle = (permission: string) => {
    const next = new Set(set);
    if (next.has(permission)) next.delete(permission);
    else next.add(permission);
    onChange([...next].sort());
  };

  const toggleAll = (resource: CatalogResource, on: boolean) => {
    const next = new Set(set);
    for (const action of resource.actions) {
      const permission = `${resource.resource}.${action}`;
      if (on) next.add(permission);
      else next.delete(permission);
    }
    onChange([...next].sort());
  };

  return (
    <div>
      {header}
      <div className="rounded-xl border border-gray-100 bg-white">
        {catalog.resources.map((resource) => (
          <ResourceRow
            key={resource.resource}
            resource={resource}
            selected={set}
            onToggle={toggle}
            onToggleAll={toggleAll}
            readOnly={readOnly}
            bn={lang === 'bn'}
          />
        ))}
      </div>
    </div>
  );
}
