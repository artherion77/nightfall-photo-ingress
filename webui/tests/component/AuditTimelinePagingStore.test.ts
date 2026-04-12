import { beforeEach, describe, expect, it, vi } from 'vitest';

import { auditTimelinePaging } from '$lib/stores/auditTimelinePaging.svelte';
import { getAuditLog } from '$lib/api/audit';

vi.mock('$lib/api/audit', () => ({
  getAuditLog: vi.fn(),
}));

function readState() {
  let snapshot: any;
  const unsubscribe = auditTimelinePaging.subscribe((value) => {
    snapshot = value;
  });
  unsubscribe();
  return snapshot;
}

function eventFixture(id: number) {
  return {
    id,
    action: id % 2 === 0 ? 'accepted' : 'rejected',
    description: `event-${id}`,
    ts: `2026-04-12T00:00:${String(id % 60).padStart(2, '0')}Z`,
    actor: 'api',
  };
}

describe('auditTimelinePaging store transitions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auditTimelinePaging.reset();
  });

  it('hydrates from initial page and tracks terminal state', () => {
    auditTimelinePaging.initialize(
      {
        events: [eventFixture(10)],
        cursor: '10',
        has_more: true,
      },
      null,
    );

    const state = readState();
    expect(state.currentPage).toBe(1);
    expect(state.entries).toHaveLength(1);
    expect(state.cursor).toBe('10');
    expect(state.terminal).toBe(false);
  });

  it('appends the next cursor page and increments current page', async () => {
    auditTimelinePaging.initialize(
      {
        events: [eventFixture(10)],
        cursor: '10',
        has_more: true,
      },
      null,
    );

    vi.mocked(getAuditLog).mockResolvedValueOnce({
      events: [eventFixture(9)],
      cursor: null,
      has_more: false,
    } as any);

    await auditTimelinePaging.loadNext();

    const state = readState();
    expect(vi.mocked(getAuditLog)).toHaveBeenCalledWith('10', 50, null);
    expect(state.currentPage).toBe(2);
    expect(state.entries.map((entry: any) => entry.id)).toEqual([10, 9]);
    expect(state.terminal).toBe(true);
  });

  it('prevents overlapping loads while an in-flight request exists', async () => {
    auditTimelinePaging.initialize(
      {
        events: [eventFixture(10)],
        cursor: '10',
        has_more: true,
      },
      null,
    );

    let resolveFetch: (value: any) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.mocked(getAuditLog).mockReturnValueOnce(pending as any);

    const p1 = auditTimelinePaging.loadNext();
    const p2 = auditTimelinePaging.loadNext();

    resolveFetch({ events: [], cursor: null, has_more: false });
    await Promise.all([p1, p2]);

    expect(vi.mocked(getAuditLog)).toHaveBeenCalledTimes(1);
  });

  it('sets error state when next-page load fails without masking previous entries', async () => {
    auditTimelinePaging.initialize(
      {
        events: [eventFixture(10)],
        cursor: '10',
        has_more: true,
      },
      null,
    );

    vi.mocked(getAuditLog).mockRejectedValueOnce(new Error('network unavailable'));

    await auditTimelinePaging.loadNext();

    const state = readState();
    expect(state.entries).toHaveLength(1);
    expect(state.error).toContain('network unavailable');
    expect(state.loading).toBe(false);
  });

  it('resets to initial state', () => {
    auditTimelinePaging.initialize(
      {
        events: [eventFixture(10)],
        cursor: '10',
        has_more: true,
      },
      'triage_accept_applied',
    );

    auditTimelinePaging.reset();
    const state = readState();

    expect(state.currentPage).toBe(0);
    expect(state.entries).toEqual([]);
    expect(state.loading).toBe(false);
    expect(state.terminal).toBe(false);
    expect(state.error).toBeNull();
  });
});
