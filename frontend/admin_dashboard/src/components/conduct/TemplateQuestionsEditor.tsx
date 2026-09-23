import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../../lib/api';
import type { ConductItem, FormQuestion, ReportTemplate } from '../../lib/api';
import { useT } from '../../lib/i18n';
import { apiErrorText } from '../../lib/apiErrors';
import { FormError } from '../common/Field';
import { btnDanger, btnPrimary, btnSecondary, selectCls } from '../common/styles';
import { QUESTION_TYPE_LABELS, asksWholeSection, itemLabel } from './shared';

/**
 * Which questions one report asks, and in what order.
 *
 * **Still no question editor here.** The questions are `forms.Question` and
 * Settings → Questions writes them; this screen only picks from the bank and
 * orders the picks. Two screens that both *create* a question would be two
 * banks pretending to be one.
 *
 * Two states, and the difference matters to whoever edits this next:
 *
 *   - **on its section** — the template asks whatever that slice of the bank
 *     holds, so a question added there tomorrow appears on the sheet by itself.
 *     The quick path, and what most institutions want.
 *   - **a chosen list** — this template asks exactly these, in this order, and
 *     a question added to the section later does *not* join it.
 *
 * Which of the two a template is on is read back from `items` —
 * `asksWholeSection` in `shared.ts` says how, and why that reading is safe.
 *
 * Ordering is arrows, not drag: HTML5 drag events do not fire from touch at
 * all, and the office phone is where half of these edits happen.
 */

export default function TemplateQuestionsEditor({
  template,
  bank,
  mayEdit,
  onSaved,
}: {
  template: ReportTemplate;
  /** The whole question bank — a chosen question may come from ANY section. */
  bank: FormQuestion[];
  mayEdit: boolean;
  onSaved: (template: ReportTemplate) => void;
}) {
  const { t, lang } = useT();

  const [draft, setDraft] = useState<number[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const serverIds = useMemo(() => template.items.map((item) => item.id), [template.items]);
  const onItsSection = asksWholeSection(template, bank);

  /** Every question this editor may need to name — the bank, plus anything the
   *  template already asks that the bank did not return (a retired question is
   *  still on the sheets it was asked on). */
  const byId = useMemo(() => {
    const map = new Map<number, Pick<ConductItem, 'id' | 'text' | 'text_bn' | 'type'>>();
    for (const item of template.items) map.set(item.id, item);
    for (const question of bank) map.set(question.id, question);
    return map;
  }, [bank, template.items]);

  const rows = draft ?? serverIds;

  const move = (from: number, to: number) => {
    if (draft === null || to < 0 || to >= draft.length) return;
    const next = [...draft];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setDraft(next);
  };

  const write = async (questions: number[]) => {
    setBusy(true);
    setError(null);
    try {
      // The whole list in one POST, never add/remove calls: two half-applied
      // requests are how an ordering ends up with two questions at position
      // three. The response is the template as it now stands.
      const saved = await apiClient.create<ReportTemplate>(
        `/report-templates/${template.id}/questions/`,
        { questions },
      );
      setDraft(null);
      onSaved(saved);
    } catch (err) {
      setError(apiErrorText(err, t, t('Could not save the questions.')));
    } finally {
      setBusy(false);
    }
  };

  const unchosen = bank
    .filter((q) => q.is_active && !rows.includes(q.id))
    .sort((a, b) => a.section.localeCompare(b.section) || a.order - b.order || a.id - b.id);

  return (
    <section className="rounded-lg border border-gray-100 bg-gray-50 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">{t('Questions on this sheet')}</h3>
          <p className="mt-0.5 text-xs leading-relaxed text-gray-600">
            {onItsSection
              ? `${t('Asks every question in section')} “${template.section}” · ${serverIds.length}`
              : `${t('Asks its own chosen questions')} · ${serverIds.length}`}
          </p>
        </div>
        {mayEdit && draft === null && (
          <button type="button" onClick={() => setDraft(serverIds)} className={btnSecondary}>
            {onItsSection ? t('Choose questions') : t('Change the questions')}
          </button>
        )}
      </div>

      <p className="mt-1 text-xs leading-relaxed text-gray-500">
        {onItsSection
          ? t('A question added to that section later joins this sheet on its own.')
          : t('A question added to that section later does not join this sheet.')}
      </p>

      <FormError message={error} />

      <ol className="mt-2 divide-y divide-gray-100 rounded-lg border border-gray-100 bg-white">
        {rows.map((id, index) => {
          const item = byId.get(id);
          return (
            <li key={id} className="flex items-center gap-2 px-2 py-1.5 sm:px-3">
              {draft !== null && (
                <div className="flex shrink-0 flex-col">
                  <button
                    type="button"
                    aria-label={t('Back')}
                    disabled={index === 0 || busy}
                    onClick={() => move(index, index - 1)}
                    className="tap min-h-[28px] rounded px-1.5 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={t('Next')}
                    disabled={index === rows.length - 1 || busy}
                    onClick={() => move(index, index + 1)}
                    className="tap min-h-[28px] rounded px-1.5 text-gray-400 hover:text-gray-700 disabled:opacity-30"
                  >
                    ↓
                  </button>
                </div>
              )}
              <span className="min-w-0 flex-1 truncate text-sm text-gray-900">
                {item ? itemLabel(item, lang) : `#${id}`}
              </span>
              <span className="shrink-0 text-xs text-gray-500">
                {item ? t(QUESTION_TYPE_LABELS[item.type] ?? item.type) : ''}
              </span>
              {draft !== null && (
                <button
                  type="button"
                  aria-label={t('Remove')}
                  disabled={busy}
                  onClick={() => setDraft(draft.filter((other) => other !== id))}
                  className="tap shrink-0 rounded px-1.5 text-sm text-red-600 hover:bg-red-50 disabled:opacity-30"
                >
                  ✕
                </button>
              )}
            </li>
          );
        })}
        {rows.length === 0 && (
          <li className="px-3 py-3 text-center text-sm text-gray-500">
            {t('This section holds no questions yet.')}
          </li>
        )}
      </ol>

      {draft !== null && (
        <div className="mt-2 space-y-2">
          <select
            value=""
            disabled={busy || unchosen.length === 0}
            onChange={(e) => {
              const id = Number(e.target.value);
              if (id) setDraft([...draft, id]);
            }}
            className={selectCls}
          >
            <option value="">
              {unchosen.length === 0 ? t('Every question is already on it.') : t('Add a question…')}
            </option>
            {unchosen.map((question) => (
              <option key={question.id} value={question.id}>
                {`${question.section} · ${itemLabel(question, lang)}`}
              </option>
            ))}
          </select>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void write(draft)}
              className={btnPrimary}
            >
              {t('Save the questions')}
            </button>
            <button type="button" disabled={busy} onClick={() => setDraft(null)} className={btnSecondary}>
              {t('Cancel')}
            </button>
            {/* An empty list is how the API says "go back to the section", and
                it is the quick path out of a list somebody no longer wants to
                keep by hand. */}
            {!onItsSection && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void write([])}
                className={btnDanger}
              >
                {t('Back to the whole section')}
              </button>
            )}
          </div>
        </div>
      )}

      <p className="mt-2 text-xs leading-relaxed text-gray-500">
        {t('Questions live in one bank, shared with the admission form. Add, reorder or retire them on Settings → Questions.')}
      </p>
      <Link to="/settings?tab=questions" className={`${btnSecondary} mt-2 inline-flex`}>
        {t('Open Settings → Questions')}
      </Link>
    </section>
  );
}
