import { describe, it, expect } from 'vitest';

describe('StatusBadge', () => {
  it('accepts known status values', () => {
    const statuses = ['ok', 'warning', 'error', 'unknown'] as const;
    expect(statuses.includes('ok')).toBe(true);
    expect(statuses.includes('warning')).toBe(true);
    expect(statuses.includes('error')).toBe(true);
    expect(statuses.includes('unknown')).toBe(true);
  });
});
