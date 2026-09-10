import { describe, it, expect } from 'vitest';
import { normalizeBdPhone, phoneInputValue } from './normalizeBdPhone';

/**
 * The phone is the login. Every one of these forms is one a real person types
 * — from a saved contact (`+880…`), from an SMS gateway export (`880…`), or by
 * hand with the dash they write it with. All of them must reach the one
 * account that exists, or the person is locked out of a system that has their
 * record.
 */
describe('normalizeBdPhone', () => {
  it('treats the same number written differently as the same number', () => {
    const forms = [
      '+8801712345678',
      '8801712345678',
      '01712345678',
      '01712-345678',
      '+88 01712-345678',
      '01712 345678',
      // Pasted from a spreadsheet cell, complete with its stray whitespace.
      '  01712345678  ',
    ];
    for (const f of forms) expect(normalizeBdPhone(f)).toBe('01712345678');
  });

  it('accepts every operator prefix in use', () => {
    for (const p of ['013', '014', '015', '016', '017', '018', '019']) {
      expect(normalizeBdPhone(`${p}12345678`)).toBe(`${p}12345678`);
    }
  });

  it('gives back nothing for what is not a BD mobile', () => {
    const notMobiles = [
      '',
      '12345',
      '02123456',        // Dhaka landline
      '01212345678',     // 012 was never allocated
      '019123456789',    // one digit too many
      '0171234567',      // one digit too few
      'not a phone',
      undefined,
      null,
    ];
    for (const f of notMobiles) expect(normalizeBdPhone(f)).toBe('');
  });

  it('keeps two different numbers different', () => {
    expect(normalizeBdPhone('01712345678')).not.toBe(normalizeBdPhone('01898765432'));
  });
});

describe('phoneInputValue', () => {
  it('keeps only digits, so the field cannot hold what the API refuses', () => {
    expect(phoneInputValue('01712-345678')).toBe('01712345678');
    expect(phoneInputValue('+88 017')).toBe('88017');
  });

  it('stops at eleven, the length of the number', () => {
    expect(phoneInputValue('017123456789999')).toBe('01712345678');
  });

  it('leaves a half-typed number alone rather than rewriting under the cursor', () => {
    expect(phoneInputValue('017')).toBe('017');
  });
});
