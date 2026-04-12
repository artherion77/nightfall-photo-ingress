import { describe, expect, it } from 'vitest';

import { relativeTimeFromIso } from '$lib/utils/relativeTime';

describe('relativeTimeFromIso', () => {
  const now = new Date('2026-04-12T12:00:00Z');

  it('returns minutes for events under an hour', () => {
    expect(relativeTimeFromIso('2026-04-12T11:35:00Z', now)).toBe('25 mins ago');
  });

  it('returns hours for events under a day', () => {
    expect(relativeTimeFromIso('2026-04-12T09:00:00Z', now)).toBe('3 hrs ago');
  });

  it('returns days for events under a week', () => {
    expect(relativeTimeFromIso('2026-04-09T12:00:00Z', now)).toBe('3 days ago');
  });

  it('falls back to short ISO date for older events', () => {
    expect(relativeTimeFromIso('2026-04-01T12:00:00Z', now)).toBe('2026-04-01');
  });
});
