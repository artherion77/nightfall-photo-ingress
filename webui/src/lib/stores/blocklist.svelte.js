import { writable } from 'svelte/store';

import { getBlocklist } from '$lib/api/blocklist';

const initial = {
  rules: [],
  loading: false,
  error: null
};

const { subscribe, update } = writable(initial);

async function loadRules() {
  update((state) => ({ ...state, loading: true, error: null }));
  try {
    const data = await getBlocklist();
    update((state) => ({ ...state, rules: data.rules ?? [], loading: false, error: null }));
  } catch (error) {
    update((state) => ({ ...state, loading: false, error: error instanceof Error ? error.message : 'Failed to load blocklist' }));
  }
}

export const blocklist = { subscribe, loadRules };
