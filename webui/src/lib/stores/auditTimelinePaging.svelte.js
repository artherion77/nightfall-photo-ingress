import { writable } from 'svelte/store';

import { getAuditLog } from '$lib/api/audit';

const DEFAULT_PAGE_SIZE = 50;

/**
 * @typedef {object} AuditTimelinePagingState
 * @property {number} currentPage
 * @property {import('$lib/api/audit').AuditEvent[]} entries
 * @property {string | null} cursor
 * @property {boolean} loading
 * @property {boolean} terminal
 * @property {string | null} filter
 * @property {number} pageSize
 * @property {string | null} error
 */

/** @returns {AuditTimelinePagingState} */
function createInitialState() {
  return {
    currentPage: 0,
    entries: [],
    cursor: null,
    loading: false,
    terminal: false,
    filter: null,
    pageSize: DEFAULT_PAGE_SIZE,
    error: null,
  };
}

const { subscribe, set, update } = writable(createInitialState());

/**
 * @param {import('$lib/api/audit').AuditPage} page
 * @param {string | null} [filter]
 */
function initialize(page, filter = null) {
  set({
    currentPage: 1,
    entries: page?.events ?? [],
    cursor: page?.cursor ?? null,
    loading: false,
    terminal: !Boolean(page?.has_more),
    filter,
    pageSize: DEFAULT_PAGE_SIZE,
    error: null,
  });
}

async function loadNext() {
  let snapshot;
  const unsubscribe = subscribe((value) => {
    snapshot = value;
  });
  unsubscribe();

  if (!snapshot || snapshot.loading || snapshot.terminal) {
    return;
  }

  update((state) => ({ ...state, loading: true, error: null }));
  try {
    const page = await getAuditLog(snapshot.cursor, snapshot.pageSize, snapshot.filter);
    update((state) => ({
      ...state,
      currentPage: state.currentPage + 1,
      entries: [...state.entries, ...(page.events ?? [])],
      cursor: page.cursor ?? null,
      terminal: !Boolean(page.has_more),
      loading: false,
      error: null,
    }));
  } catch (error) {
    update((state) => ({
      ...state,
      loading: false,
      error: error instanceof Error ? error.message : 'Failed to load audit timeline',
    }));
  }
}

/** @param {string | null} filter */
async function setFilter(filter) {
  update((state) => ({
    ...state,
    currentPage: 0,
    entries: [],
    cursor: null,
    terminal: false,
    loading: true,
    error: null,
    filter,
  }));

  try {
    const page = await getAuditLog(null, DEFAULT_PAGE_SIZE, filter);
    set({
      currentPage: 1,
      entries: page.events ?? [],
      cursor: page.cursor ?? null,
      loading: false,
      terminal: !Boolean(page.has_more),
      filter,
      pageSize: DEFAULT_PAGE_SIZE,
      error: null,
    });
  } catch (error) {
    update((state) => ({
      ...state,
      loading: false,
      error: error instanceof Error ? error.message : 'Failed to filter audit timeline',
      terminal: state.entries.length > 0 ? state.terminal : false,
    }));
  }
}

function reset() {
  set(createInitialState());
}

export const auditTimelinePaging = {
  subscribe,
  initialize,
  loadNext,
  setFilter,
  reset,
};
