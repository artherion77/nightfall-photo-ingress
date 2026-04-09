import { beforeEach, describe, expect, it, vi } from 'vitest';

import { stagingQueue } from '$lib/stores/stagingQueue.svelte';

const toastPushMock = vi.fn();
const fetchMock = vi.fn();

vi.mock('$lib/stores/toast.svelte', () => ({
  toast: {
    push: (...args: any[]) => toastPushMock(...args),
  },
}));

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    headers: new Headers(),
  } as Response;
}

function readState(store: any) {
  let value: any;
  const unsubscribe = store.subscribe((state: any) => {
    value = state;
  });
  unsubscribe();
  return value;
}

describe('stagingQueue triage revalidation', () => {
  beforeEach(() => {
    toastPushMock.mockReset();
    fetchMock.mockReset();
    stagingQueue.clearQueue();
    vi.stubGlobal('fetch', fetchMock);
  });

  it('revalidates queue after successful triage and backfills server changes', async () => {
    stagingQueue.hydrate([
      { sha256: 'a', filename: 'a.jpg' },
      { sha256: 'b', filename: 'b.jpg' },
      { sha256: 'c', filename: 'c.jpg' },
    ]);
    stagingQueue.setActiveIndex(1);

    fetchMock.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/triage/b/reject') {
        expect(init?.method).toBe('POST');
        return jsonResponse({ action_correlation_id: 'reject-1', item_id: 'b', state: 'rejected' });
      }

      if (input === '/api/v1/staging?limit=20') {
        return jsonResponse({
          items: [
            { sha256: 'a', filename: 'a.jpg' },
            { sha256: 'c', filename: 'c.jpg' },
            { sha256: 'd', filename: 'd.jpg' },
          ],
          total: 3,
          cursor: null,
        });
      }

      throw new Error(`Unexpected fetch: ${input}`);
    });

    await stagingQueue.triageItem('reject', 'b', 'reject-1');

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/triage/b/reject');
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'POST' });
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/staging?limit=20');
    expect(readState(stagingQueue)).toMatchObject({
      items: [
        { sha256: 'a', filename: 'a.jpg' },
        { sha256: 'c', filename: 'c.jpg' },
        { sha256: 'd', filename: 'd.jpg' },
      ],
      total: 3,
      activeIndex: 1,
      loading: false,
      error: null,
    });
  });

  it('supports consecutive triage operations while keeping queue in sync with server', async () => {
    stagingQueue.hydrate([
      { sha256: 'a', filename: 'a.jpg' },
      { sha256: 'b', filename: 'b.jpg' },
    ]);

    fetchMock.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/triage/a/accept') {
        expect(init?.method).toBe('POST');
        return jsonResponse({ action_correlation_id: 'accept-1', item_id: 'a', state: 'accepted' });
      }

      if (input === '/api/v1/triage/b/reject') {
        expect(init?.method).toBe('POST');
        return jsonResponse({ action_correlation_id: 'reject-2', item_id: 'b', state: 'rejected' });
      }

      if (input === '/api/v1/staging?limit=20' && fetchMock.mock.calls.length === 2) {
        return jsonResponse({
          items: [
            { sha256: 'b', filename: 'b.jpg' },
            { sha256: 'c', filename: 'c.jpg' },
          ],
          total: 2,
          cursor: null,
        });
      }

      if (input === '/api/v1/staging?limit=20' && fetchMock.mock.calls.length === 4) {
        return jsonResponse({
          items: [
            { sha256: 'c', filename: 'c.jpg' },
            { sha256: 'd', filename: 'd.jpg' },
          ],
          total: 2,
          cursor: null,
        });
      }

      throw new Error(`Unexpected fetch: ${input}`);
    });

    await stagingQueue.triageItem('accept', 'a', 'accept-1');
    await stagingQueue.triageItem('reject', 'b', 'reject-2');

    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/triage/a/accept');
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'POST' });
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/staging?limit=20');
    expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/v1/triage/b/reject');
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({ method: 'POST' });
    expect(fetchMock.mock.calls[3]?.[0]).toBe('/api/v1/staging?limit=20');
    expect(readState(stagingQueue)).toMatchObject({
      items: [
        { sha256: 'c', filename: 'c.jpg' },
        { sha256: 'd', filename: 'd.jpg' },
      ],
      total: 2,
      activeIndex: 0,
      loading: false,
      error: null,
    });
  });
});