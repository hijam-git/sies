import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiClient } from '../../lib/api';
import type {
  FormQuestion,
  FormTemplate,
  QuestionOption,
  QuestionPrintStyle,
  QuestionType,
} from '../../lib/api';
import { usePermissions } from '../../lib/auth-context';
import { useT } from '../../lib/i18n';
import { apiErrorText, apiFieldErrors } from '../../lib/apiErrors';
import BaseModal from '../common/BaseModal';
import Field, { FieldGrid, FieldWide, FormError } from '../common/Field';
import { btnPrimary, btnSecondary, inputCls, selectCls } from '../common/styles';

/**
 * Settings → Questions — the question bank (`docs/07` §5, §9).
 *
 * The form's variable part: what an institution asks beyond the fixed identity
 * fields. Grouped by **section**, because a `question_set` block prints one
 * section, and ordered within it, because the order is the order they print in.
 *
 * The rule worth knowing before editing anything here is **§5.2**: a question
 * that binds to a student field (`maps_to`) writes that field and stores no
 * answer. A question either maps to a field or stores an answer, never both —
 * otherwise "previous institution" lives in two places, they disagree within a
 * month, and no report built on either can be trusted. The editor says so where
 * the field is, not in a doc nobody opens.
 */

const TYPES: { value: QuestionType; label: string }[] = [
  { value: 'short_text', label: 'Short text' },
  { value: 'description', label: 'Description' },
  { value: 'single_choice', label: 'Single choice' },
  { value: 'multi_choice', label: 'Multiple choice' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'yes_no', label: 'Yes / no' },
];

const PRINT_STYLES: { value: QuestionPrintStyle; label: string }[] = [
  { value: 'inline', label: 'Label and rule on one line' },
  { value: 'block', label: 'Label above, ruled lines below' },
  { value: 'checkbox', label: 'Choices as ☐ boxes' },
];

const CHOICE_TYPES: QuestionType[] = ['single_choice', 'multi_choice'];

interface QuestionDraft {
  id: number | null;
  template: string;
  section: string;
  text: string;
  text_bn: string;
  type: QuestionType;
  options: QuestionOption[];
  is_required: boolean;
  print_style: QuestionPrintStyle;
  answer_lines: number;
  maps_to: string;
  order: number;
  is_active: boolean;
}

function emptyDraft(section: string, order: number): QuestionDraft {
  return {
    id: null,
    template: '',
    section,
    text: '',
    text_bn: '',
    type: 'short_text',
    options: [],
    is_required: false,
    print_style: 'inline',
    answer_lines: 1,
    maps_to: '',
    order,
    is_active: true,
  };
}

export default function QuestionsTab() {
  const { t } = useT();
  const { can } = usePermissions();
  const mayEdit = can('settings', 'update');

  const [questions, setQuestions] = useState<FormQuestion[]>([]);
  const [templates, setTemplates] = useState<FormTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<QuestionDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [dragged, setDragged] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [rows, templateRows] = await Promise.all([
        apiClient.listAll<FormQuestion>('/questions/', '?ordering=order'),
        apiClient.listAll<FormTemplate>('/form-templates/', '?ordering=name').catch(() => []),
      ]);
      setQuestions(rows);
      setTemplates(templateRows);
    } catch (err) {
      setLoadError(apiErrorText(err, t, t('Could not load the questions.')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Deferred a tick, like every other list screen here: state written straight
  // from an effect body cascades a render before the first paint.
  useEffect(() => {
    const timer = setTimeout(() => void load(), 0);
    return () => clearTimeout(timer);
  }, [load]);

  /** Section → its questions, in print order. */
  const sections = useMemo(() => {
    const grouped = new Map<string, FormQuestion[]>();
    [...questions]
      .sort((a, b) => a.order - b.order || a.id - b.id)
      .forEach((q) => grouped.set(q.section, [...(grouped.get(q.section) ?? []), q]));
    return [...grouped.entries()];
  }, [questions]);

  const mappableFields = questions[0]?.mappable_fields ?? [];

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const body: Record<string, unknown> = {
      template: draft.template ? Number(draft.template) : null,
      section: draft.section.trim() || 'general',
      text: draft.text.trim(),
      text_bn: draft.text_bn.trim(),
      type: draft.type,
      options: CHOICE_TYPES.includes(draft.type) ? draft.options : [],
      is_required: draft.is_required,
      print_style: draft.print_style,
      answer_lines: draft.answer_lines,
      maps_to: draft.maps_to,
      order: draft.order,
      is_active: draft.is_active,
    };
    try {
      if (draft.id === null) await apiClient.create<FormQuestion>('/questions/', body);
      else await apiClient.patch<FormQuestion>('/questions/', draft.id, body);
      setDraft(null);
      await load();
    } catch (err) {
      setFieldErrors(apiFieldErrors(err));
      setFormError(apiErrorText(err, t, t('Could not save this question.')));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (question: FormQuestion) => {
    setFormError(null);
    try {
      await apiClient.destroy('/questions/', question.id);
      await load();
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not delete this question.')));
    }
  };

  /**
   * Reorder within a section, and write it through.
   *
   * `order` is renumbered in tens for the whole section rather than swapping two
   * values: a bank seeded 10/20/30 and then edited by hand collects duplicate
   * orders, and two questions with the same order print in whatever order the
   * database felt like.
   */
  const move = async (section: string, from: number, to: number) => {
    const rows = sections.find(([name]) => name === section)?.[1] ?? [];
    if (to < 0 || to >= rows.length || from === to) return;
    const next = [...rows];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);

    // Optimistic: the list is already in the new order on screen while the
    // writes go out, because a reorder that visibly waits gets clicked twice.
    setQuestions((current) =>
      current.map((q) => {
        const index = next.findIndex((x) => x.id === q.id);
        return index === -1 ? q : { ...q, order: (index + 1) * 10 };
      }),
    );

    try {
      for (const [index, row] of next.entries()) {
        const order = (index + 1) * 10;
        if (row.order !== order) await apiClient.patch<FormQuestion>('/questions/', row.id, { order });
      }
    } catch (err) {
      setFormError(apiErrorText(err, t, t('Could not save the new order.')));
      await load();
    }
  };

  const openNew = (section: string) => {
    const rows = sections.find(([name]) => name === section)?.[1] ?? [];
    setDraft(emptyDraft(section, (rows.length + 1) * 10));
    setFormError(null);
    setFieldErrors({});
  };

  const openEdit = (question: FormQuestion) => {
    setDraft({
      id: question.id,
      template: question.template === null ? '' : String(question.template),
      section: question.section,
      text: question.text,
      text_bn: question.text_bn,
      type: question.type,
      options: question.options ?? [],
      is_required: question.is_required,
      print_style: question.print_style,
      answer_lines: question.answer_lines,
      maps_to: question.maps_to,
      order: question.order,
      is_active: question.is_active,
    });
    setFormError(null);
    setFieldErrors({});
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-3">
        {mayEdit && (
          <button type="button" onClick={() => openNew('admission')} className={btnPrimary}>
            {t('New question')}
          </button>
        )}
      </div>

      <FormError message={loadError ?? formError} />

      {loading && <p className="py-8 text-center text-sm text-gray-500">{t('Loading...')}</p>}

      {!loading && sections.length === 0 && (
        <p className="rounded-xl border border-gray-100 bg-white p-8 text-center text-sm text-gray-500 shadow-sm">
          {t('No questions yet.')}
        </p>
      )}

      {sections.map(([section, rows]) => (
        <section key={section} className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              {`${t('Section')} · ${section}`}
            </h3>
            {mayEdit && (
              <button type="button" onClick={() => openNew(section)} className={btnSecondary}>
                {t('Add to this section')}
              </button>
            )}
          </div>

          <ul className="space-y-2">
            {rows.map((question, index) => (
              <li
                key={question.id}
                // Drag on a desktop, arrows on a phone — HTML5 drag events do
                // not fire from touch at all, and the office phone is where
                // half of these edits happen.
                draggable={mayEdit}
                onDragStart={() => setDragged(question.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const from = rows.findIndex((r) => r.id === dragged);
                  setDragged(null);
                  if (from !== -1) void move(section, from, index);
                }}
                className={`flex items-start gap-2 rounded-lg border p-3 ${
                  dragged === question.id ? 'border-blue-400 opacity-60' : 'border-gray-200'
                }`}
              >
                {mayEdit && (
                  <div className="flex shrink-0 flex-col">
                    <button
                      type="button"
                      aria-label={t('Back')}
                      disabled={index === 0}
                      onClick={() => void move(section, index, index - 1)}
                      className="tap min-h-[36px] rounded px-2 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label={t('Next')}
                      disabled={index === rows.length - 1}
                      onClick={() => void move(section, index, index + 1)}
                      className="tap min-h-[36px] rounded px-2 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                    >
                      ↓
                    </button>
                  </div>
                )}

                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900">
                    {question.text_bn || question.text}
                  </p>
                  <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-gray-500">
                    <span>{t(TYPES.find((x) => x.value === question.type)?.label ?? question.type)}</span>
                    <span>{question.print_style}</span>
                    {question.maps_to && (
                      <span className="text-amber-700">{`${t('Writes')}: ${question.maps_to}`}</span>
                    )}
                    {!question.is_active && <span className="text-gray-400">{t('Inactive')}</span>}
                  </p>
                </div>

                {mayEdit && (
                  <div className="flex shrink-0 flex-col gap-1 sm:flex-row">
                    <button type="button" onClick={() => openEdit(question)} className={btnSecondary}>
                      {t('Edit')}
                    </button>
                    <button
                      type="button"
                      onClick={() => void remove(question)}
                      className="tap rounded-lg border border-red-200 px-3 text-sm font-medium text-red-700 hover:bg-red-50"
                    >
                      {t('Delete')}
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}

      <BaseModal
        isOpen={draft !== null}
        onClose={() => setDraft(null)}
        title={draft?.id === null ? t('New question') : t('Edit question')}
        maxWidth="2xl"
        footer={
          <div className="flex gap-2">
            <button type="button" onClick={() => setDraft(null)} className={`${btnSecondary} flex-1`}>
              {t('Cancel')}
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className={`${btnPrimary} flex-1`}
            >
              {saving ? t('Saving…') : t('Save')}
            </button>
          </div>
        }
      >
        {draft && (
          <div className="space-y-4">
            <FormError message={formError} />

            <FieldGrid>
              <FieldWide>
                <Field label={t('Question (Bangla)')} error={fieldErrors.text_bn} required>
                  <input
                    value={draft.text_bn}
                    onChange={(e) => setDraft({ ...draft, text_bn: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              </FieldWide>
              <FieldWide>
                <Field label={t('Question (English)')} error={fieldErrors.text} required>
                  <input
                    value={draft.text}
                    onChange={(e) => setDraft({ ...draft, text: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              </FieldWide>

              <Field label={t('Type')} error={fieldErrors.type}>
                <select
                  value={draft.type}
                  onChange={(e) => setDraft({ ...draft, type: e.target.value as QuestionType })}
                  className={selectCls}
                >
                  {TYPES.map((x) => (
                    <option key={x.value} value={x.value}>
                      {t(x.label)}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label={t('Print style')} error={fieldErrors.print_style}>
                <select
                  value={draft.print_style}
                  onChange={(e) =>
                    setDraft({ ...draft, print_style: e.target.value as QuestionPrintStyle })
                  }
                  className={selectCls}
                >
                  {PRINT_STYLES.map((x) => (
                    <option key={x.value} value={x.value}>
                      {t(x.label)}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label={t('Section')} error={fieldErrors.section}>
                <input
                  value={draft.section}
                  onChange={(e) => setDraft({ ...draft, section: e.target.value })}
                  className={inputCls}
                />
              </Field>

              <Field
                label={t('Template')}
                hint={t('Leave blank and every form of this institution may ask it.')}
                error={fieldErrors.template}
              >
                <select
                  value={draft.template}
                  onChange={(e) => setDraft({ ...draft, template: e.target.value })}
                  className={selectCls}
                >
                  <option value="">{t('Every template')}</option>
                  {templates.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name_bn || x.name}
                    </option>
                  ))}
                </select>
              </Field>

              {draft.type === 'description' && (
                <Field label={t('Ruled lines to print')} error={fieldErrors.answer_lines}>
                  <input
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={12}
                    value={draft.answer_lines}
                    onChange={(e) =>
                      setDraft({ ...draft, answer_lines: Number(e.target.value) || 1 })
                    }
                    className={inputCls}
                  />
                </Field>
              )}

              <FieldWide>
                <Field
                  label={t('Writes this student field')}
                  hint={t('A question bound to a field writes it and stores no separate answer, so the two can never disagree.')}
                  error={fieldErrors.maps_to}
                >
                  <select
                    value={draft.maps_to}
                    onChange={(e) => setDraft({ ...draft, maps_to: e.target.value })}
                    className={selectCls}
                  >
                    <option value="">{t('Stores its own answer')}</option>
                    {mappableFields.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </Field>
              </FieldWide>
            </FieldGrid>

            {CHOICE_TYPES.includes(draft.type) && (
              <div className="space-y-2">
                <span className="block text-sm font-medium text-gray-700">{t('Options')}</span>
                {fieldErrors.options && (
                  <p className="text-xs font-medium text-red-600">{fieldErrors.options}</p>
                )}
                {draft.options.map((option, index) => (
                  <div key={index} className="flex flex-col gap-2 sm:flex-row">
                    <input
                      value={option.label_bn}
                      placeholder={t('Printed label (Bangla)')}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          options: draft.options.map((o, i) =>
                            i === index ? { ...o, label_bn: e.target.value } : o,
                          ),
                        })
                      }
                      className={inputCls}
                    />
                    <input
                      value={option.value}
                      placeholder={t('Stored value')}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          options: draft.options.map((o, i) =>
                            i === index ? { ...o, value: e.target.value } : o,
                          ),
                        })
                      }
                      className={`${inputCls} sm:w-40`}
                    />
                    <button
                      type="button"
                      aria-label={t('Delete item')}
                      onClick={() =>
                        setDraft({
                          ...draft,
                          options: draft.options.filter((_, i) => i !== index),
                        })
                      }
                      className="tap shrink-0 rounded px-3 text-red-600 hover:bg-red-50"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    setDraft({
                      ...draft,
                      options: [...draft.options, { value: '', label: '', label_bn: '' }],
                    })
                  }
                  className={btnSecondary}
                >
                  {t('Add option')}
                </button>
              </div>
            )}

            <label className="flex min-h-[44px] items-center gap-3">
              <input
                type="checkbox"
                checked={draft.is_required}
                onChange={(e) => setDraft({ ...draft, is_required: e.target.checked })}
                className="h-5 w-5 rounded border-gray-300 text-blue-600"
              />
              <span className="text-sm text-gray-700">
                {t('Required on the data-entry screen')}
              </span>
            </label>
            <label className="flex min-h-[44px] items-center gap-3">
              <input
                type="checkbox"
                checked={draft.is_active}
                onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })}
                className="h-5 w-5 rounded border-gray-300 text-blue-600"
              />
              <span className="text-sm text-gray-700">{t('Prints on the form')}</span>
            </label>
          </div>
        )}
      </BaseModal>
    </div>
  );
}
