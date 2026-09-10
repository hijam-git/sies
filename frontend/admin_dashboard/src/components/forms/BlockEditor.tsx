import { useRef, useState } from 'react';
import type { FormBlock, FormLabelledPair, FormOfficePanel } from '../../lib/api';
import { useT } from '../../lib/i18n';
import Field, { FieldGrid } from '../common/Field';
import { btnSecondary, inputCls, selectCls } from '../common/styles';
import { BLOCK_TYPES, blockLabel } from './blockTypes';

/**
 * The template's blocks, as an ordered list (`docs/07` §9).
 *
 * **Not a WYSIWYG page designer, and deliberately.** A madrasah administrator
 * needs to change the pledge wording and the questions, not drag text boxes to
 * coordinates — and a designer would let them build a form the renderer cannot
 * print. Each block here is its own small form of exactly the keys
 * `forms/blocks.py` accepts for that type; anything else is refused on save.
 *
 * The error a rejected save produces is hung on the block that caused it. The
 * backend names it (`blocks[3] (prose) …`), so a form of thirteen blocks does
 * not answer a typo with a toast saying something somewhere is wrong.
 */

/** A list of plain strings — pledge items, letterhead lines, office rules. */
function StringList({
  label,
  items,
  onChange,
  placeholder,
  rows = 1,
}: {
  label: string;
  items: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  rows?: number;
}) {
  const { t } = useT();
  return (
    <div>
      <span className="mb-1 block text-sm font-medium text-gray-700">{label}</span>
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index} className="flex items-start gap-2">
            <textarea
              value={item}
              rows={rows}
              placeholder={placeholder}
              onChange={(e) =>
                onChange(items.map((x, i) => (i === index ? e.target.value : x)))
              }
              className={inputCls}
            />
            <div className="flex shrink-0 flex-col">
              <button
                type="button"
                aria-label={t('Back')}
                disabled={index === 0}
                onClick={() => {
                  const next = [...items];
                  [next[index - 1], next[index]] = [next[index], next[index - 1]];
                  onChange(next);
                }}
                className="tap min-h-[36px] rounded px-2 text-gray-400 hover:text-gray-700 disabled:opacity-30"
              >
                ↑
              </button>
              <button
                type="button"
                aria-label={t('Delete item')}
                onClick={() => onChange(items.filter((_, i) => i !== index))}
                className="tap min-h-[36px] rounded px-2 text-red-600 hover:text-red-700"
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => onChange([...items, ''])}
        className={`${btnSecondary} mt-2`}
      >
        {t('Add line')}
      </button>
    </div>
  );
}

/** `{label, value}` rows — a meta row and a field grid are both made of these. */
function PairList({
  pairs,
  onChange,
  placeholders,
}: {
  pairs: FormLabelledPair[];
  onChange: (next: FormLabelledPair[]) => void;
  placeholders: Record<string, string[]>;
}) {
  const { t } = useT();
  const update = (index: number, patch: Partial<FormLabelledPair>) =>
    onChange(pairs.map((p, i) => (i === index ? { ...p, ...patch } : p)));

  return (
    <div className="space-y-2">
      {pairs.map((pair, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-lg border border-gray-200 p-2 sm:flex-row">
          <input
            value={pair.label ?? ''}
            onChange={(e) => update(index, { label: e.target.value })}
            placeholder={t('Printed label')}
            className={`${inputCls} sm:w-44`}
          />
          <div className="flex-1">
            <PlaceholderInput
              value={pair.value ?? ''}
              onChange={(value) => update(index, { value })}
              placeholders={placeholders}
            />
          </div>
          <button
            type="button"
            aria-label={t('Delete item')}
            onClick={() => onChange(pairs.filter((_, i) => i !== index))}
            className="tap shrink-0 rounded px-3 text-red-600 hover:bg-red-50"
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...pairs, { label: '', value: '' }])} className={btnSecondary}>
        {t('Add field')}
      </button>
    </div>
  );
}

/**
 * A single-line value with the placeholder picker beside it.
 *
 * The picker is generated from `placeholder_groups`, which the template
 * endpoint serves from the same table `placeholders.py` validates against — so
 * the offered list and the accepted list cannot drift (`docs/07` §4).
 */
function PlaceholderInput({
  value,
  onChange,
  placeholders,
}: {
  value: string;
  onChange: (next: string) => void;
  placeholders: Record<string, string[]>;
}) {
  const { t } = useT();
  const ref = useRef<HTMLInputElement>(null);

  const insert = (name: string) => {
    const el = ref.current;
    const token = `{{${name}}}`;
    const at = el?.selectionStart ?? value.length;
    onChange(value.slice(0, at) + token + value.slice(at));
    // Focus back on the field, not the picker: the next thing typed is the rest
    // of the sentence.
    window.setTimeout(() => el?.focus(), 0);
  };

  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      <input
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
      <select
        value=""
        onChange={(e) => e.target.value && insert(e.target.value)}
        aria-label={t('Insert a placeholder')}
        className={`${selectCls} sm:w-52`}
      >
        <option value="">{t('Insert a placeholder')}</option>
        {Object.entries(placeholders).map(([group, names]) => (
          <optgroup key={group} label={group}>
            {names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}

/** The paragraph editor — the block an administrator actually edits. */
function ProseFields({
  block,
  onChange,
  placeholders,
}: {
  block: FormBlock;
  onChange: (patch: Partial<FormBlock>) => void;
  placeholders: Record<string, string[]>;
}) {
  const { t } = useT();
  const ref = useRef<HTMLTextAreaElement>(null);

  const insert = (name: string) => {
    const el = ref.current;
    const current = block.text_bn ?? '';
    const at = el?.selectionStart ?? current.length;
    onChange({ text_bn: current.slice(0, at) + `{{${name}}}` + current.slice(at) });
    window.setTimeout(() => el?.focus(), 0);
  };

  return (
    <div className="space-y-3">
      <Field
        label={t('Printed text (Bangla)')}
        hint={t('A placeholder that has no value prints as a blank rule to write on.')}
      >
        <textarea
          ref={ref}
          value={block.text_bn ?? ''}
          rows={4}
          onChange={(e) => onChange({ text_bn: e.target.value })}
          className={inputCls}
        />
      </Field>

      <select
        value=""
        onChange={(e) => e.target.value && insert(e.target.value)}
        aria-label={t('Insert a placeholder')}
        className={selectCls}
      >
        <option value="">{t('Insert a placeholder')}</option>
        {Object.entries(placeholders).map(([group, names]) => (
          <optgroup key={group} label={group}>
            {names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </optgroup>
        ))}
      </select>

      <Field
        label={t('English text')}
        hint={t('The editor’s reference. The Bangla is what prints.')}
      >
        <textarea
          value={block.text ?? ''}
          rows={2}
          onChange={(e) => onChange({ text: e.target.value })}
          className={inputCls}
        />
      </Field>

      <FieldGrid>
        <Field label={t('Alignment')}>
          <select
            value={block.align ?? ''}
            onChange={(e) => onChange({ align: e.target.value })}
            className={selectCls}
          >
            <option value="">{t('Left')}</option>
            <option value="center">{t('Centre')}</option>
            <option value="right">{t('Right')}</option>
          </select>
        </Field>
        <label className="flex min-h-[44px] items-center gap-3 self-end">
          <input
            type="checkbox"
            checked={block.indent ?? false}
            onChange={(e) => onChange({ indent: e.target.checked })}
            className="h-5 w-5 rounded border-gray-300 text-blue-600"
          />
          <span className="text-sm text-gray-700">{t('Indent the first line')}</span>
        </label>
      </FieldGrid>
    </div>
  );
}

/** One block's own fields — exactly the keys its type accepts. */
function BlockFields({
  block,
  onChange,
  placeholders,
}: {
  block: FormBlock;
  onChange: (patch: Partial<FormBlock>) => void;
  placeholders: Record<string, string[]>;
}) {
  const { t } = useT();

  switch (block.type) {
    case 'letterhead':
      return (
        <div className="space-y-3">
          <StringList
            label={t('Arabic lines')}
            items={block.lines_ar ?? []}
            onChange={(lines_ar) => onChange({ lines_ar })}
          />
          <StringList
            label={t('Lines')}
            items={block.lines ?? []}
            onChange={(lines) => onChange({ lines })}
          />
          <label className="flex min-h-[44px] items-center gap-3">
            <input
              type="checkbox"
              checked={block.show_logo ?? false}
              onChange={(e) => onChange({ show_logo: e.target.checked })}
              className="h-5 w-5 rounded border-gray-300 text-blue-600"
            />
            <span className="text-sm text-gray-700">{t('Show the logo')}</span>
          </label>
        </div>
      );

    case 'meta_row':
      return (
        <PairList
          pairs={block.fields ?? []}
          onChange={(fields) => onChange({ fields })}
          placeholders={placeholders}
        />
      );

    case 'prose':
      return <ProseFields block={block} onChange={onChange} placeholders={placeholders} />;

    case 'field_grid':
      return (
        <div className="space-y-3">
          <FieldGrid>
            <Field label={t('Title (Bangla)')}>
              <input
                value={block.title_bn ?? ''}
                onChange={(e) => onChange({ title_bn: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label={t('Columns')}>
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={4}
                value={block.columns ?? 2}
                onChange={(e) => onChange({ columns: Number(e.target.value) || 1 })}
                className={inputCls}
              />
            </Field>
          </FieldGrid>
          <PairList
            pairs={block.fields ?? []}
            onChange={(fields) => onChange({ fields })}
            placeholders={placeholders}
          />
        </div>
      );

    case 'question_set':
      return (
        <FieldGrid>
          <Field
            label={t('Section')}
            hint={t('Prints every active question of the question bank in this section.')}
          >
            <input
              value={block.section ?? ''}
              onChange={(e) => onChange({ section: e.target.value })}
              className={inputCls}
            />
          </Field>
          <Field label={t('Title (Bangla)')}>
            <input
              value={block.title_bn ?? ''}
              onChange={(e) => onChange({ title_bn: e.target.value })}
              className={inputCls}
            />
          </Field>
        </FieldGrid>
      );

    case 'bullet_list':
      return (
        <div className="space-y-3">
          <FieldGrid>
            <Field label={t('Title (Bangla)')}>
              <input
                value={block.title_bn ?? ''}
                onChange={(e) => onChange({ title_bn: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label={t('Marker')}>
              <select
                value={block.style ?? 'bullet'}
                onChange={(e) => onChange({ style: e.target.value })}
                className={selectCls}
              >
                <option value="bullet">{t('Bullets')}</option>
                <option value="number">{t('Numbers')}</option>
                <option value="none">{t('None')}</option>
              </select>
            </Field>
          </FieldGrid>
          <StringList
            label={t('Items')}
            rows={2}
            items={block.items ?? []}
            onChange={(items) => onChange({ items })}
          />
        </div>
      );

    case 'office_box':
      return (
        <div className="space-y-3">
          <FieldGrid>
            <Field label={t('Title')}>
              <input
                value={block.title ?? ''}
                onChange={(e) => onChange({ title: e.target.value })}
                className={inputCls}
              />
            </Field>
            <Field label={t('Title (Bangla)')}>
              <input
                value={block.title_bn ?? ''}
                onChange={(e) => onChange({ title_bn: e.target.value })}
                className={inputCls}
              />
            </Field>
          </FieldGrid>
          <StringList
            label={t('Ruled lines')}
            items={block.lines ?? []}
            onChange={(lines) => onChange({ lines })}
          />
          <div className="space-y-2">
            <span className="block text-sm font-medium text-gray-700">{t('Panels')}</span>
            {(block.panels ?? []).map((panel: FormOfficePanel, index: number) => (
              <div key={index} className="space-y-2 rounded-lg border border-gray-200 p-2">
                <input
                  value={panel.title_bn ?? ''}
                  placeholder={t('Panel title (Bangla)')}
                  onChange={(e) =>
                    onChange({
                      panels: (block.panels ?? []).map((p, i) =>
                        i === index ? { ...p, title_bn: e.target.value } : p,
                      ),
                    })
                  }
                  className={inputCls}
                />
                <StringList
                  label={t('Ruled lines')}
                  items={panel.lines ?? []}
                  onChange={(lines) =>
                    onChange({
                      panels: (block.panels ?? []).map((p, i) =>
                        i === index ? { ...p, lines } : p,
                      ),
                    })
                  }
                />
                <button
                  type="button"
                  onClick={() =>
                    onChange({ panels: (block.panels ?? []).filter((_, i) => i !== index) })
                  }
                  className="tap rounded px-3 text-sm text-red-600 hover:bg-red-50"
                >
                  {t('Remove panel')}
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => onChange({ panels: [...(block.panels ?? []), { title_bn: '', lines: [''] }] })}
              className={btnSecondary}
            >
              {t('Add panel')}
            </button>
          </div>
        </div>
      );

    case 'signature_row':
      return (
        <div className="space-y-3">
          <StringList
            label={t('Captions')}
            items={block.captions ?? []}
            onChange={(captions) => onChange({ captions })}
          />
          <Field label={t('Alignment')}>
            <select
              value={block.align ?? ''}
              onChange={(e) => onChange({ align: e.target.value })}
              className={selectCls}
            >
              <option value="">{t('Spread across the page')}</option>
              <option value="right">{t('Right')}</option>
            </select>
          </Field>
        </div>
      );

    case 'spacer':
      return (
        <Field label={t('Height')} hint="6mm">
          <input
            value={block.height ?? ''}
            onChange={(e) => onChange({ height: e.target.value })}
            className={inputCls}
          />
        </Field>
      );

    default:
      return (
        <p className="text-sm text-gray-500">{t('This block has nothing to configure.')}</p>
      );
  }
}

export default function BlockEditor({
  blocks,
  onChange,
  placeholders,
  /** `{blockIndex: message}` from the last rejected save. */
  blockErrors,
  disabled = false,
}: {
  blocks: FormBlock[];
  onChange: (next: FormBlock[]) => void;
  placeholders: Record<string, string[]>;
  blockErrors: Record<number, string>;
  disabled?: boolean;
}) {
  const { t } = useT();
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  const patch = (index: number, values: Partial<FormBlock>) =>
    onChange(blocks.map((b, i) => (i === index ? { ...b, ...values } : b)));

  const move = (from: number, to: number) => {
    if (to < 0 || to >= blocks.length) return;
    const next = [...blocks];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
    setOpen(null);
  };

  /** The one line that says what this block will print, so the list can be read
   *  without opening thirteen panels. */
  const summary = (block: FormBlock): string => {
    if (block.type === 'prose') return (block.text_bn || block.text || '').slice(0, 70);
    if (block.type === 'bullet_list') return `${(block.items ?? []).length} ${t('items')}`;
    if (block.type === 'question_set') return `${t('Section')}: ${block.section ?? ''}`;
    if (block.type === 'meta_row' || block.type === 'field_grid')
      return (block.fields ?? []).map((f) => f.label ?? '').join(' · ').slice(0, 70);
    if (block.type === 'signature_row') return (block.captions ?? []).join(' · ');
    if (block.type === 'office_box') return block.title_bn || block.title || '';
    if (block.type === 'letterhead') return (block.lines ?? []).join(' · ').slice(0, 70);
    return '';
  };

  return (
    <div className="space-y-3">
      {blocks.length === 0 && (
        <p className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 py-6 text-center text-sm text-gray-500">
          {t('This template has no blocks yet.')}
        </p>
      )}

      {blocks.map((block, index) => {
        const error = blockErrors[index];
        return (
          <div
            key={index}
            className={`rounded-lg border bg-white ${error ? 'border-red-300' : 'border-gray-200'}`}
          >
            <div className="flex items-start gap-2 p-3">
              <div className="flex shrink-0 flex-col">
                <button
                  type="button"
                  aria-label={t('Back')}
                  disabled={disabled || index === 0}
                  onClick={() => move(index, index - 1)}
                  className="tap min-h-[36px] rounded px-2 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={t('Next')}
                  disabled={disabled || index === blocks.length - 1}
                  onClick={() => move(index, index + 1)}
                  className="tap min-h-[36px] rounded px-2 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                >
                  ↓
                </button>
              </div>

              <button
                type="button"
                onClick={() => setOpen(open === index ? null : index)}
                className="min-w-0 flex-1 text-left"
              >
                <span className="block text-sm font-semibold text-gray-900">
                  {t(blockLabel(block.type))}
                </span>
                <span className="block truncate text-xs text-gray-500">{summary(block)}</span>
              </button>

              <button
                type="button"
                aria-label={t('Delete item')}
                disabled={disabled}
                onClick={() => {
                  onChange(blocks.filter((_, i) => i !== index));
                  setOpen(null);
                }}
                className="tap shrink-0 rounded px-3 text-red-600 hover:bg-red-50 disabled:opacity-30"
              >
                ×
              </button>
            </div>

            {error && (
              <p className="border-t border-red-100 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                {error}
              </p>
            )}

            {open === index && (
              <div className="border-t border-gray-100 p-3">
                <BlockFields
                  block={block}
                  onChange={(values) => patch(index, values)}
                  placeholders={placeholders}
                />
              </div>
            )}
          </div>
        );
      })}

      {!disabled && (
        <div>
          <button type="button" onClick={() => setAdding(!adding)} className={btnSecondary}>
            {adding ? t('Close') : t('Add a block')}
          </button>
          {adding && (
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {BLOCK_TYPES.map((def) => (
                <button
                  key={def.type}
                  type="button"
                  onClick={() => {
                    onChange([...blocks, def.make()]);
                    setAdding(false);
                    setOpen(blocks.length);
                  }}
                  className="rounded-lg border border-gray-200 p-3 text-left hover:border-blue-400 hover:bg-blue-50"
                >
                  <span className="block text-sm font-semibold text-gray-900">{t(def.label)}</span>
                  <span className="block text-xs text-gray-500">{t(def.hint)}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
