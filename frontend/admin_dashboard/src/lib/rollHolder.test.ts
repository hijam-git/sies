import { describe, expect, it } from 'vitest';
import { ApiError, rollHolder } from './api';

// The roll dialog asks "swap?" off this, so a refusal it cannot read would
// fall back to a bare error and the swap would never be offered.
describe('rollHolder', () => {
  it('reads the holder out of a roll_taken refusal', () => {
    const err = new ApiError(400, 'Roll 3 belongs to Bilal', {
      code: 'roll_taken',
      errors: {
        roll: ['Roll 3 belongs to Bilal'],
        holder_enrolment: ['42'],
        holder_name: ['Bilal'],
        holder_name_bn: ['বিলাল'],
        holder_code: ['SIES-000007'],
        holder_active: ['true'],
      },
    });
    expect(rollHolder(err)).toEqual({
      enrolment: 42,
      name: 'Bilal',
      name_bn: 'বিলাল',
      code: 'SIES-000007',
      active: true,
    });
  });

  it('is null for any other failure', () => {
    expect(rollHolder(new ApiError(400, 'x', { code: 'validation_error', errors: {} }))).toBeNull();
    expect(rollHolder(new Error('network'))).toBeNull();
  });
});
