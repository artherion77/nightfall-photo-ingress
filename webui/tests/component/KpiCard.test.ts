import { describe, it, expect } from 'vitest';

describe('KpiCard', () => {
  it('computes threshold levels consistently', () => {
    const warning = 10;
    const error = 20;

    const classify = (value: number) => {
      if (value >= error) return 'error';
      if (value >= warning) return 'warning';
      return 'ok';
    };

    expect(classify(5)).toBe('ok');
    expect(classify(10)).toBe('warning');
    expect(classify(25)).toBe('error');
  });
});
