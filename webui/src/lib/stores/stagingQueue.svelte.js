import { writable } from 'svelte/store';

import { getStagingPage } from '$lib/api/staging';
import { generateIdempotencyKey, postAccept, postDefer, postReject } from '$lib/api/triage';
import { toast } from '$lib/stores/toast.svelte';

const initial = {
  items: [],
  cursor: null,
  total: 0,
  activeIndex: 0,
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
      activeIndex: cursor ? state.activeIndex : 0,
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

function hydrate(items = []) {
  update((state) => ({
    ...state,
    items,
    total: items.length,
    activeIndex: 0,
    error: null
  }));
}

function setActiveIndex(index) {
  update((state) => {
    if (state.items.length === 0) {
      return { ...state, activeIndex: 0 };
    }
    const next = Math.max(0, Math.min(index, state.items.length - 1));
    return { ...state, activeIndex: next };
  });
}

function shiftActive(delta) {
  update((state) => {
    if (state.items.length === 0) {
      return state;
    }
    const raw = state.activeIndex + delta;
    const next = Math.max(0, Math.min(raw, state.items.length - 1));
    return { ...state, activeIndex: next };
  });
}

async function triageItem(action, itemId, idempotencyKey) {
  let snapshot = null;
  const key = idempotencyKey ?? generateIdempotencyKey();

  update((state) => {
    snapshot = state;
    const removedIndex = state.items.findIndex((item) => item.sha256 === itemId);
    if (removedIndex === -1) {
      return state;
    }

    const items = state.items.filter((item) => item.sha256 !== itemId);
    const activeIndex = Math.min(state.activeIndex, Math.max(items.length - 1, 0));

    return {
      ...state,
      items,
      total: Math.max(0, state.total - 1),
      activeIndex,
      error: null
    };
  });

  try {
    if (action === 'accept') {
      await postAccept(itemId, key);
      return;
    }
    if (action === 'reject') {
      await postReject(itemId, key);
      return;
    }
    if (action === 'defer') {
      await postDefer(itemId, key);
      return;
    }
    throw new Error(`Unsupported triage action: ${action}`);
  } catch (error) {
    if (snapshot) {
      set(snapshot);
    }
    const message = error instanceof Error ? error.message : 'Triage action failed';
    update((state) => ({ ...state, error: message }));
    toast.push(message, 'error');
    throw error;
  }
}

export const stagingQueue = {
  subscribe,
  loadPage,
  clearQueue,
  hydrate,
  setActiveIndex,
  shiftActive,
  triageItem
};
