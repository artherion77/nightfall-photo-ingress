import { writable } from 'svelte/store';

import { getStagingPage } from '$lib/api/staging';

const initial = {
  items: [],
  cursor: null,
  total: 0,
  loading: false,
  error: null
};

const { subscribe, update, set } = writable(initial);

async function loadPage(cursor = null, limit = 20) {
  update((state) => ({ ...state, loading: true, error: null }));
  try {
    const page = await getStagingPage(cursor, limit);
    update((state) => ({
      ...state,
      items: cursor ? [...state.items, ...(page.items ?? [])] : (page.items ?? []),
      cursor: page.cursor ?? null,
      total: page.total ?? state.total,
      loading: false,
      error: null
    }));
  } catch (error) {
    update((state) => ({ ...state, loading: false, error: error instanceof Error ? error.message : 'Failed to load staging queue' }));
  }
}

function clearQueue() {
  set(initial);
}

export const stagingQueue = { subscribe, loadPage, clearQueue };
