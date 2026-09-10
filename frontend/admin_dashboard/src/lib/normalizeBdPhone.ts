/**
 * Canonicalising a Bangladeshi mobile number.
 *
 * Load-bearing, because the phone IS the login (`CLAUDE.md` §1). A counter
 * clerk who types `+8801712345678` and a principal who typed `01712-345678`
 * when creating the account are naming the same person, and the account they
 * are naming has exactly one row. Compared as raw text they are three
 * different people.
 *
 * Same rule as the server's `core.bd.normalize_bd_phone`, deliberately — the
 * two are compared against each other constantly, so they must agree
 * character for character.
 */

/** A BD mobile: 01, then an operator digit 3–9, then eight more. */
export const BD_MOBILE_RE = /^01[3-9]\d{8}$/;

/**
 * `'+88 01712-345678'` → `'01712345678'`.
 *
 * Returns `''` — not the input, and not null — for anything that is not a BD
 * mobile. An empty string is falsy and cannot be mistaken for a number, so a
 * caller that forgets to check compares against nothing rather than against
 * a landline it half-cleaned.
 */
export function normalizeBdPhone(raw: string | undefined | null): string {
  let d = (raw || '').replace(/\D/g, '');
  if (d.startsWith('88')) d = d.slice(2);
  // A number typed without its leading zero, as it is written internationally.
  if (d.length === 10 && d.startsWith('1')) d = '0' + d;
  return BD_MOBILE_RE.test(d) ? d : '';
}

/**
 * What the login box shows while it is being typed.
 *
 * Digits only and never longer than 11, so the field cannot hold something the
 * backend will refuse — but it does NOT canonicalise mid-type, because
 * rewriting `017` into something else under someone's cursor makes the field
 * feel broken. `normalizeBdPhone` runs on submit.
 */
export function phoneInputValue(raw: string): string {
  return raw.replace(/\D/g, '').slice(0, 11);
}
