import { writable } from 'svelte/store';

import { getEffectiveConfig } from '$lib/api/config';

const initial = {
  kpi_thresholds: {},
  loading: false,
  error: null
};

const { subscribe, set, update } = writable(initial);

async function load() {
  update((state) => ({ ...state, loading: true, error: null }));
  try {
    const cfg = await getEffectiveConfig();
    set({
      ...cfg,
      kpi_thresholds: cfg.kpi_thresholds ?? {},
      loading: false,
      error: null
    });
  } catch (error) {
    update((state) => ({ ...state, loading: false, error: error instanceof Error ? error.message : 'Failed to load config' }));
  }
}

export const configStore = { subscribe, load };
