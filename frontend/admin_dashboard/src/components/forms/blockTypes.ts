import type { FormBlock, FormBlockType } from '../../lib/api';

/**
 * The add-block menu, and what a freshly added block starts as.
 *
 * The list mirrors `forms/blocks.py`'s `BLOCK_SCHEMA` — the same eleven types,
 * with the same required keys — because the backend refuses anything else on
 * save. Offering a twelfth here would be offering a block that cannot be saved.
 *
 * A new block starts with its **required** keys already filled with something
 * printable. A block added empty would fail validation the moment the admin
 * pressed Save, and the first thing they would see is an error about a block
 * they had not typed into yet.
 */
export interface BlockTypeDef {
  type: FormBlockType;
  /** English source string; the editor runs it through `t()`. */
  label: string;
  hint: string;
  make: () => FormBlock;
}

export const BLOCK_TYPES: BlockTypeDef[] = [
  {
    type: 'letterhead',
    label: 'Letterhead',
    hint: 'The institution’s Arabic, Bangla and English names, and its address.',
    make: () => ({
      type: 'letterhead',
      lines_ar: ['{{branch.name_ar}}'],
      lines: ['{{branch.name_bn}}', '{{branch.name}}', '{{branch.address_bn}}'],
      show_logo: true,
    }),
  },
  {
    type: 'meta_row',
    label: 'Form number row',
    hint: 'Form no · admission no · session · date, across one line.',
    make: () => ({
      type: 'meta_row',
      fields: [
        { label: 'ফরম নং', value: '{{form.form_no}}' },
        { label: 'তারিখ', value: '{{form.date}}' },
      ],
    }),
  },
  {
    type: 'prose',
    label: 'Paragraph',
    hint: 'Template text with fill-in-the-blank placeholders — the application letter.',
    make: () => ({ type: 'prose', text: '', text_bn: '', indent: true }),
  },
  {
    type: 'field_grid',
    label: 'Field grid',
    hint: 'A two-column labelled grid of the applicant’s details.',
    make: () => ({
      type: 'field_grid',
      title_bn: 'আবেদনকারীর তথ্যাবলী',
      columns: 2,
      fields: [
        { label: 'নাম :', value: '{{student.name_bn}}' },
        { label: 'জন্ম তারিখ :', value: '{{student.dob}}' },
      ],
    }),
  },
  {
    type: 'question_set',
    label: 'Questions',
    hint: 'Prints one section of the question bank.',
    make: () => ({ type: 'question_set', section: 'admission' }),
  },
  {
    type: 'bullet_list',
    label: 'Bulleted list',
    hint: 'The pledges and the guardian’s rules.',
    make: () => ({ type: 'bullet_list', title_bn: '', style: 'number', items: [''] }),
  },
  {
    type: 'office_box',
    label: 'Office-use panel',
    hint: 'A bordered box of blank ruled lines, filled in by hand after the interview.',
    make: () => ({
      type: 'office_box',
      title: 'Office use only',
      title_bn: 'অফিস কর্তৃক পূরণীয়',
      lines: [''],
      panels: [],
    }),
  },
  {
    type: 'signature_row',
    label: 'Signature line',
    hint: 'One or more signature spaces with captions under them.',
    make: () => ({ type: 'signature_row', captions: ['আবেদনকারীর স্বাক্ষর'] }),
  },
  {
    type: 'spacer',
    label: 'Space',
    hint: 'Vertical space.',
    make: () => ({ type: 'spacer', height: '6mm' }),
  },
  {
    type: 'divider',
    label: 'Rule',
    hint: 'A horizontal line.',
    make: () => ({ type: 'divider' }),
  },
  {
    type: 'page_break',
    label: 'Page break',
    hint: 'Everything after this starts on the next sheet.',
    make: () => ({ type: 'page_break' }),
  },
];

export function blockLabel(type: FormBlockType): string {
  return BLOCK_TYPES.find((b) => b.type === type)?.label ?? type;
}

/**
 * `blocks[3] (prose) has unknown key(s) …` → `3`.
 *
 * The backend names the offending block in its message (`forms/blocks.py`), so
 * the editor can hang the error on THAT block rather than showing a toast that
 * says something somewhere is wrong with a form of thirteen blocks.
 */
export function blockIndexInError(message: string): number | null {
  const match = /blocks\[(\d+)\]/.exec(message);
  return match ? Number(match[1]) : null;
}
