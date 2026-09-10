/**
 * Money and numbers, written the way a Bangladeshi office writes them.
 *
 * BDT is hard-coded platform-wide — there is no currency setting and there
 * will not be one. Grouping is Indian (1,20,000), not Western (120,000),
 * because that is what a receipt has to match when somebody checks it by hand.
 */

export const BDT_SYMBOL = '৳';

/**
 * `formatBDT(1250)` → `"৳1,250"`.
 *
 * Accepts a string as well as a number: the API sends every `DecimalField` as
 * a string, deliberately, so that no amount ever passes through a float.
 */
export function formatBDT(amount: number | string | null | undefined): string {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount;
  if (n === null || n === undefined || Number.isNaN(n)) return `${BDT_SYMBOL}0`;
  return `${BDT_SYMBOL}${Math.round(n).toLocaleString('en-IN')}`;
}

/**
 * The same money with paisa kept: `formatBDTExact("1250.50")` → `"৳1,250.50"`.
 *
 * For anything that must reconcile to the last poisha — a receipt line, a
 * ledger row, a fee balance. Rounding those to whole taka makes a column of
 * figures stop adding up to its own total.
 */
export function formatBDTExact(amount: number | string | null | undefined): string {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount;
  if (n === null || n === undefined || Number.isNaN(n)) return `${BDT_SYMBOL}0.00`;
  return `${BDT_SYMBOL}${n.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/**
 * The same money as it goes back INTO a number input — plain digits, no ৳ and
 * no separator, two decimal places without the trailing `.00` noise:
 * `moneyInputValue(600)` → `"600"`, `moneyInputValue(1000 / 3)` → `"333.33"`.
 */
export function moneyInputValue(n: number): string {
  return (Math.round(n * 100) / 100).toFixed(2).replace(/\.00$/, '');
}

const BN_DIGITS = ['০', '১', '২', '৩', '৪', '৫', '৬', '৭', '৮', '৯'];

/**
 * `toBanglaDigits("৳1,250")` → `"৳১,২৫০"`.
 *
 * A printed form, a receipt and a mark sheet are read by people who expect
 * Bangla numerals; the screen mostly is not, because a clerk cross-checking
 * against a bank statement needs the digits to look like the statement's.
 * So this is applied where a document is produced, never globally.
 */
export function toBanglaDigits(s: string | number): string {
  return String(s).replace(/\d/g, (d) => BN_DIGITS[Number(d)]);
}

/** `formatNumber(1234)` → `"1,234"`. Student counts, marks, attendance days. */
export function formatNumber(n: number | string | null | undefined): string {
  const v = typeof n === 'string' ? parseFloat(n) : n;
  if (v === null || v === undefined || Number.isNaN(v)) return '0';
  return v.toLocaleString('en-IN');
}

/**
 * `formatPercent(0.8734)` → `"87.3%"`.
 *
 * One decimal place, because attendance and pass rates are compared between
 * classes and whole numbers hide the difference between 89.4 and 89.6.
 */
export function formatPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return '—';
  return `${(fraction * 100).toFixed(1)}%`;
}
