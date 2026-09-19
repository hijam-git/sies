import { describe, expect, it } from 'vitest';
import {
  compareMoney, fromPaisa, subtractMoney, sumMoney, takaInWordsBn, takaInWordsEn, toPaisa,
} from './money';

/**
 * Money arithmetic is on `CLAUDE.md` §8.4's list of things that must have
 * tests, and the reason is the first case below: a float gets `0.30000000000004`
 * and a dues column that will not add up to its own total.
 */

describe('poisha arithmetic', () => {
  it('parses the API\'s decimal strings exactly', () => {
    expect(toPaisa('1250.50')).toBe(125050);
    expect(toPaisa('0.01')).toBe(1);
    expect(toPaisa('1200.00')).toBe(120000);
    // A single decimal place is tenths, not hundredths.
    expect(toPaisa('5.5')).toBe(550);
    expect(toPaisa('')).toBe(0);
    expect(toPaisa(null)).toBe(0);
    expect(toPaisa('-40.25')).toBe(-4025);
    // A third decimal rounds rather than truncating: it is only ever produced
    // by a figure computed on screen, and truncating it made the "balance
    // remaining" preview and the printed receipt disagree by a poisha.
    expect(toPaisa('1250.509')).toBe(125051);
    expect(toPaisa('1250.504')).toBe(125050);
    expect(toPaisa('0.999')).toBe(100);
  });

  it('round-trips through the string form the API uses', () => {
    expect(fromPaisa(125050)).toBe('1250.50');
    expect(fromPaisa(5)).toBe('0.05');
    expect(fromPaisa(0)).toBe('0.00');
  });

  it('adds without the float error that a naive sum has', () => {
    // 0.1 + 0.2 !== 0.3 in JS. This is the whole point of the module.
    expect(sumMoney(['0.10', '0.20'])).toBe('0.30');
    expect(sumMoney(['1200.00', '500.00', '0.50'])).toBe('1700.50');
    expect(sumMoney([])).toBe('0.00');
  });

  it('subtracts a part payment from a balance', () => {
    expect(subtractMoney('1200.00', '500.00')).toBe('700.00');
    expect(subtractMoney('1200.00', '1200.00')).toBe('0.00');
  });

  it('compares without parsing to a float', () => {
    expect(compareMoney('500.00', '1200.00')).toBe(-1);
    expect(compareMoney('1200.00', '1200.00')).toBe(0);
    expect(compareMoney('1200.01', '1200.00')).toBe(1);
  });
});

describe('taka in words — the line under the figures on a receipt', () => {
  it('writes Bangla in the crore/lakh grouping', () => {
    expect(takaInWordsBn('0.00')).toBe('শূন্য টাকা মাত্র');
    expect(takaInWordsBn('1200.00')).toBe('এক হাজার দুই শত টাকা মাত্র');
    expect(takaInWordsBn('1250.50')).toBe('এক হাজার দুই শত পঞ্চাশ টাকা পঞ্চাশ পয়সা মাত্র');
    // Sixty-one is its own word — not "ষাট এক", which is what a tens+units
    // construction would produce.
    expect(takaInWordsBn('61.00')).toBe('একষট্টি টাকা মাত্র');
    expect(takaInWordsBn('125000.00')).toBe('এক লক্ষ পঁচিশ হাজার টাকা মাত্র');
  });

  it('writes English in the same grouping, not in millions', () => {
    expect(takaInWordsEn('1250.50')).toBe('One thousand two hundred fifty taka fifty poisha only');
    expect(takaInWordsEn('125000.00')).toBe('One lakh twenty-five thousand taka only');
  });
});
