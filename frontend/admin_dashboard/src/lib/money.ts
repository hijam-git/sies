/**
 * Money arithmetic without a float, and money in Bangla words.
 *
 * `lib/format.ts` renders an amount the API sent. This file is for the two
 * things a fee screen cannot avoid doing itself:
 *
 *  1. **Adding a column of amounts the server gave no total for.** The dues
 *     screen groups by student and by class; `/api/fees/summary/` totals by
 *     status only, and there is no endpoint that totals by either grouping. So
 *     the addition happens here — in **integer poisha**, never in a float.
 *     `0.1 + 0.2` is `0.30000000000000004`, and a dues column that is four
 *     poisha out is a column an accountant stops trusting.
 *  2. **Taka in words**, which every receipt in Bangladesh carries under the
 *     figures so that a "1" cannot be turned into a "7" after the fact.
 *
 * Rule of thumb for the screens: if the API returned a total, print that total.
 * Only reach for `sumMoney` when it did not, and say on the screen which
 * figures were added here — `docs/02` §4.5 makes the server the authority and
 * these helpers do not change that.
 */

/**
 * `"1250.50"` → `125050`. The API sends every `DecimalField` as a string
 * precisely so the value never passes through a float, and parsing the two
 * halves separately keeps that promise all the way to the sum.
 */
export function toPaisa(amount: string | number | null | undefined): number {
  if (amount === null || amount === undefined) return 0;
  const raw = String(amount).trim();
  if (!raw) return 0;

  const negative = raw.startsWith('-');
  const digits = raw.replace(/^[+-]/, '');
  const [whole = '0', fraction = ''] = digits.split('.');

  const wholeDigits = whole.replace(/\D/g, '') || '0';
  // Pad, then cut: "5" is fifty poisha, "5678" is fifty-six (the API never
  // sends more than two, but a truncating parse is the safe one).
  // Pad to three, then round the third away: "1250.509" is 125051 poisha, not
  // 125050. The API sends two decimals, but a preview computed on screen can
  // produce a third, and truncating it made the receipt and the "balance
  // remaining" line disagree by a poisha.
  const fractionDigits = `${fraction.replace(/\D/g, '')}000`.slice(0, 3);

  const value = Number(wholeDigits) * 100 + Math.round(Number(fractionDigits) / 10);
  return Number.isFinite(value) ? (negative ? -value : value) : 0;
}

/** `125050` → `"1250.50"`. The same shape the API sends, so the result can go
 *  straight into `formatBDTExact` or back into a request body. */
export function fromPaisa(paisa: number): string {
  const rounded = Math.round(paisa);
  const sign = rounded < 0 ? '-' : '';
  const abs = Math.abs(rounded);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}

/** Exact total of a column of API amounts, as a decimal string. */
export function sumMoney(amounts: (string | number | null | undefined)[]): string {
  return fromPaisa(amounts.reduce<number>((total, a) => total + toPaisa(a), 0));
}

/** `a - b`, exact, as a decimal string. The balance left after a part payment. */
export function subtractMoney(a: string | number, b: string | number): string {
  return fromPaisa(toPaisa(a) - toPaisa(b));
}

/** `-1`, `0` or `1`. For "is this payment more than the balance?" — asked
 *  before the request goes out, so the clerk sees it rather than a 400. */
export function compareMoney(a: string | number, b: string | number): number {
  const pa = toPaisa(a);
  const pb = toPaisa(b);
  return pa === pb ? 0 : pa < pb ? -1 : 1;
}

export function isPositiveMoney(a: string | number): boolean {
  return toPaisa(a) > 0;
}

// ── Taka in words ─────────────────────────────────────────────────────────

// Bangla has its own word for every number to ninety-nine — none of them is
// built from a tens word plus a units word — so the table is the only correct
// way to do this. Anything shorter produces "ষাট এক" for sixty-one.
const BN_UNDER_HUNDRED = [
  'শূন্য', 'এক', 'দুই', 'তিন', 'চার', 'পাঁচ', 'ছয়', 'সাত', 'আট', 'নয়',
  'দশ', 'এগারো', 'বারো', 'তেরো', 'চৌদ্দ', 'পনেরো', 'ষোলো', 'সতেরো', 'আঠারো', 'উনিশ',
  'বিশ', 'একুশ', 'বাইশ', 'তেইশ', 'চব্বিশ', 'পঁচিশ', 'ছাব্বিশ', 'সাতাশ', 'আটাশ', 'ঊনত্রিশ',
  'ত্রিশ', 'একত্রিশ', 'বত্রিশ', 'তেত্রিশ', 'চৌত্রিশ', 'পঁয়ত্রিশ', 'ছত্রিশ', 'সাঁইত্রিশ', 'আটত্রিশ', 'ঊনচল্লিশ',
  'চল্লিশ', 'একচল্লিশ', 'বিয়াল্লিশ', 'তেতাল্লিশ', 'চুয়াল্লিশ', 'পঁয়তাল্লিশ', 'ছেচল্লিশ', 'সাতচল্লিশ', 'আটচল্লিশ', 'ঊনপঞ্চাশ',
  'পঞ্চাশ', 'একান্ন', 'বায়ান্ন', 'তিপ্পান্ন', 'চুয়ান্ন', 'পঞ্চান্ন', 'ছাপ্পান্ন', 'সাতান্ন', 'আটান্ন', 'ঊনষাট',
  'ষাট', 'একষট্টি', 'বাষট্টি', 'তেষট্টি', 'চৌষট্টি', 'পঁয়ষট্টি', 'ছেষট্টি', 'সাতষট্টি', 'আটষট্টি', 'ঊনসত্তর',
  'সত্তর', 'একাত্তর', 'বাহাত্তর', 'তিয়াত্তর', 'চুয়াত্তর', 'পঁচাত্তর', 'ছিয়াত্তর', 'সাতাত্তর', 'আটাত্তর', 'ঊনআশি',
  'আশি', 'একাশি', 'বিরাশি', 'তিরাশি', 'চুরাশি', 'পঁচাশি', 'ছিয়াশি', 'সাতাশি', 'আটাশি', 'ঊননব্বই',
  'নব্বই', 'একানব্বই', 'বিরানব্বই', 'তিরানব্বই', 'চুরানব্বই', 'পঁচানব্বই', 'ছিয়ানব্বই', 'সাতানব্বই', 'আটানব্বই', 'নিরানব্বই',
];

// Crore, lakh, thousand, hundred — the South Asian grouping, which is what a
// Bangladeshi receipt is read against. Western thousands would be wrong here in
// the same way the digit grouping would be.
const BN_SCALES: [number, string][] = [
  [10000000, 'কোটি'],
  [100000, 'লক্ষ'],
  [1000, 'হাজার'],
  [100, 'শত'],
];

function bnWholeInWords(n: number): string {
  if (n === 0) return BN_UNDER_HUNDRED[0];

  const parts: string[] = [];
  let rest = n;
  for (const [value, name] of BN_SCALES) {
    const count = Math.floor(rest / value);
    if (count > 0) {
      // Recursive for কোটি alone: everything below it is under a hundred once
      // the larger scales have been taken out, but a crore count can itself run
      // into lakhs on a whole institution's yearly figure.
      parts.push(`${value === 10000000 ? bnWholeInWords(count) : BN_UNDER_HUNDRED[count]} ${name}`);
      rest -= count * value;
    }
  }
  if (rest > 0) parts.push(BN_UNDER_HUNDRED[rest]);
  return parts.join(' ');
}

/**
 * `"1250.50"` → `"এক হাজার দুই শত পঞ্চাশ টাকা পঞ্চাশ পয়সা মাত্র"`.
 *
 * The line printed under the figures on the receipt. "মাত্র" ("only") closes
 * it, which is what stops a number being extended by hand afterwards — the
 * whole reason the words are there.
 */
export function takaInWordsBn(amount: string | number): string {
  const paisa = Math.abs(Math.round(toPaisa(amount)));
  const taka = Math.floor(paisa / 100);
  const poisha = paisa % 100;

  const words = [`${bnWholeInWords(taka)} টাকা`];
  if (poisha > 0) words.push(`${BN_UNDER_HUNDRED[poisha]} পয়সা`);
  words.push('মাত্র');
  return words.join(' ');
}

const EN_UNDER_TWENTY = [
  'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
  'seventeen', 'eighteen', 'nineteen',
];
const EN_TENS = [
  '', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety',
];

function enUnderHundred(n: number): string {
  if (n < 20) return EN_UNDER_TWENTY[n];
  const tens = EN_TENS[Math.floor(n / 10)];
  const units = n % 10;
  return units ? `${tens}-${EN_UNDER_TWENTY[units]}` : tens;
}

function enWholeInWords(n: number): string {
  if (n === 0) return 'zero';
  const parts: string[] = [];
  let rest = n;
  // Crore and lakh, not million and billion: the receipt is an English rendering
  // of a Bangladeshi figure, and a guardian checking it against the Bangla line
  // above has to be able to line the two up.
  for (const [value, name] of [
    [10000000, 'crore'],
    [100000, 'lakh'],
    [1000, 'thousand'],
    [100, 'hundred'],
  ] as [number, string][]) {
    const count = Math.floor(rest / value);
    if (count > 0) {
      parts.push(`${value === 10000000 ? enWholeInWords(count) : enUnderHundred(count)} ${name}`);
      rest -= count * value;
    }
  }
  if (rest > 0) parts.push(enUnderHundred(rest));
  return parts.join(' ');
}

/** `"1250.50"` → `"One thousand two hundred fifty taka fifty poisha only"`. */
export function takaInWordsEn(amount: string | number): string {
  const paisa = Math.abs(Math.round(toPaisa(amount)));
  const taka = Math.floor(paisa / 100);
  const poisha = paisa % 100;

  const words = [`${enWholeInWords(taka)} taka`];
  if (poisha > 0) words.push(`${enUnderHundred(poisha)} poisha`);
  words.push('only');
  const line = words.join(' ');
  return line.charAt(0).toUpperCase() + line.slice(1);
}
