import { describe, it, expect } from 'vitest';

// Utility functions extracted from PollRuntimeChart logic for unit testing
// These mirror the pure computation in the component without mounting it.

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

interface PollHistoryEntry {
  day: string;
  duration_s: number;
}

function fillEntries(history: PollHistoryEntry[]): PollHistoryEntry[] {
  if (history.length >= 7) return history.slice(0, 7);
  return [
    ...DAY_LABELS.slice(0, 7 - history.length).map((day) => ({ day, duration_s: 0 })),
    ...history,
  ];
}

function computeYMax(entries: PollHistoryEntry[]): number {
  const maxDur = Math.max(...entries.map((e) => e.duration_s), 0.01);
  return Math.max(5, Math.ceil(maxDur / 5) * 5);
}

describe('PollRuntimeChart logic', () => {
  it('fills missing entries with zero up to 7 items', () => {
    const result = fillEntries([{ day: 'Sun', duration_s: 10 }]);
    expect(result).toHaveLength(7);
    expect(result[6]).toEqual({ day: 'Sun', duration_s: 10 });
    expect(result[0].duration_s).toBe(0);
  });

  it('uses first 7 entries when more than 7 are provided', () => {
    const input = Array.from({ length: 9 }, (_, i) => ({ day: 'Mon', duration_s: i }));
    const result = fillEntries(input);
    expect(result).toHaveLength(7);
  });

  it('computes yMax rounded up to nearest 5 (minimum 5)', () => {
    expect(computeYMax([{ day: 'Mon', duration_s: 0 }])).toBe(5);
    expect(computeYMax([{ day: 'Mon', duration_s: 3 }])).toBe(5);
    expect(computeYMax([{ day: 'Mon', duration_s: 6 }])).toBe(10);
    expect(computeYMax([{ day: 'Mon', duration_s: 23 }])).toBe(25);
  });

  it('returns 7 entries with valid day labels when given full history', () => {
    const full = DAY_LABELS.map((day) => ({ day, duration_s: 5 }));
    const result = fillEntries(full);
    expect(result).toHaveLength(7);
    result.forEach((e) => expect(DAY_LABELS).toContain(e.day));
  });
});
