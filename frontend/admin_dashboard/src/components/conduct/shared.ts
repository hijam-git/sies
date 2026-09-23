import type {
  ConductItem,
  ConductStudent,
  ConductValue,
  QuestionOption,
  QuestionType,
} from '../../lib/api';

/**
 * The small decisions the conduct sheet and its history both make.
 *
 * Here rather than inside the grid because the student detail modal renders the
 * same answers from a different endpoint, and two readings of what `true` means
 * is two screens that disagree about whether a boy prayed.
 */

/** The name to print — Bangla when the record carries it, which it nearly
 *  always does for a madrasah's roll. */
export function studentName(student: { name: string; name_bn: string }): string {
  return student.name_bn || student.name;
}

/** A question's own wording, in the reader's language. */
export function itemLabel(
  item: { text: string; text_bn: string },
  lang: string,
): string {
  return (lang === 'bn' ? item.text_bn || item.text : item.text || item.text_bn) || '';
}

/**
 * A question's choices as `{value, label}`, whichever shape they were stored in.
 *
 * `forms.Question.options` accepts both `["ভালো", …]` and
 * `[{value, label, label_bn}]` — the backend's own `_options()` reads both —
 * so the screen must too, or an institution that typed plain strings gets a
 * picker with no entries and no explanation.
 */
export function itemOptions(item: ConductItem, lang: string): QuestionOption[] {
  const raw = (item.options ?? []) as unknown as Array<QuestionOption | string>;
  return raw.map((option) => {
    if (typeof option === 'string') {
      return { value: option, label: option, label_bn: option };
    }
    const value = String(option.value ?? option.label ?? '');
    const label = lang === 'bn'
      ? option.label_bn || option.label || value
      : option.label || value;
    return { value, label, label_bn: option.label_bn || label };
  }).filter((option) => option.value !== '');
}

/**
 * Is this the value already on file?
 *
 * Order-insensitive for a multi-choice: the same two boxes ticked in the other
 * order is not an edit, and counting it as one puts a row in the save that has
 * nothing to say.
 */
export function sameValue(a: ConductValue, b: ConductValue): boolean {
  const blankA = a === null || a === undefined || a === '';
  const blankB = b === null || b === undefined || b === '';
  if (blankA || blankB) return blankA && blankB;
  if (Array.isArray(a) || Array.isArray(b)) {
    const left = [...(Array.isArray(a) ? a : [String(a)])].map(String).sort();
    const right = [...(Array.isArray(b) ? b : [String(b)])].map(String).sort();
    return left.length === right.length && left.every((v, i) => v === right[i]);
  }
  return String(a) === String(b);
}

/** `null → true → false → null` — the whole yes/no cell, one tap per step.
 *  A teacher marking forty boys at নামাজ taps once each; the two further steps
 *  exist for the one they got wrong. */
export function cycleYesNo(value: ConductValue): ConductValue {
  if (value === true) return false;
  if (value === false) return null;
  return true;
}

/** What a filled answer reads as — on the history list and in the cell's
 *  accessible label. `yes` / `no` are translated by the caller. */
export function displayValue(
  item: Pick<ConductItem, 'type'> & Partial<ConductItem>,
  value: ConductValue,
  t: (s: string) => string,
): string {
  if (value === null || value === undefined || value === '') return '—';
  if (item.type === 'yes_no') return value ? t('Yes') : t('No');
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
}

/** The answer as the screen should show it: the unsaved edit if there is one,
 *  otherwise what the server sent. */
export function effectiveAnswer(
  student: ConductStudent,
  itemId: number,
  draft: Map<number, DraftRow>,
): ConductValue {
  const row = draft.get(student.enrolment);
  if (row && Object.prototype.hasOwnProperty.call(row.answers, String(itemId))) {
    return row.answers[String(itemId)];
  }
  return student.answers[String(itemId)] ?? null;
}

/** The remark, same rule. */
export function effectiveRemarks(
  student: ConductStudent,
  draft: Map<number, DraftRow>,
): string {
  const row = draft.get(student.enrolment);
  return row?.remarks ?? student.remarks ?? '';
}

/** One student's unsaved edits. `answers` holds ONLY the items that changed —
 *  the endpoint writes what it is given and leaves the rest alone, so sending
 *  the whole row would re-stamp answers nobody touched. */
export interface DraftRow {
  answers: Record<string, ConductValue>;
  remarks: string;
}

/**
 * A question type as the office reads it.
 *
 * The same English labels Settings → Questions uses, so both screens hit the
 * same Bangla entry rather than growing two words for `yes_no`.
 */
export const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  short_text: 'Short text',
  description: 'Description',
  single_choice: 'Single choice',
  multi_choice: 'Multiple choice',
  number: 'Number',
  date: 'Date',
  yes_no: 'Yes / no',
};
