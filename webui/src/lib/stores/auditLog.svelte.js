import { writable } from 'svelte/store';

import { getAuditLog } from '$lib/api/audit';

const initial = {
  events: [],
  cursor: null,
  hasMore: false,
  filter: null,
  loading: false,
  error: null
};

const { subscribe, update, set } = writable(initial);

async function loadMore() {
  let current;
  const unsub = subscribe((value) => {
    current = value;
  });
  unsub();

  update((state) => ({ ...state, loading: true, error: null }));
  try {
    const page = await getAuditLog(current.cursor, 50, current.filter);
    update((state) => ({
      ...state,
      events: [...state.events, ...(page.events ?? [])],
      cursor: page.cursor ?? null,
      hasMore: page.has_more ?? false,
      loading: false,
      error: null
    }));
  } catch (error) {
    update((state) => ({ ...state, loading: false, error: error instanceof Error ? error.message : 'Failed to load audit log' }));
  }
}

async function setFilter(action) {
  set({ ...initial, filter: action, loading: true });
  try {
    const page = await getAuditLog(null, 50, action);
    update((state) => ({
      ...state,
      events: page.events ?? [],
      cursor: page.cursor ?? null,
      hasMore: page.has_more ?? false,
      loading: false,
      error: null
    }));
  } catch (error) {
    update((state) => ({ ...state, loading: false, error: error instanceof Error ? error.message : 'Failed to filter audit log' }));
  }
}

export const auditLog = { subscribe, loadMore, setFilter };
