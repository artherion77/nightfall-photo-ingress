import { writable } from 'svelte/store';

import { getStagingPage } from '$lib/api/staging';
import { getHealth } from '$lib/api/health';

const initial = {
  pending_count: 0,
  accepted_today: 0,
  rejected_today: 0,
  live_photo_pairs: 0,
  last_poll_duration_s: 0,
  loading: false,
  error: null
};

const { subscribe, update } = writable(initial);

async function load() {
  update((state) => ({ ...state, loading: true, error: null }));
  try {
    const [staging, health] = await Promise.all([getStagingPage(null, 1), getHealth()]);
    update((state) => ({
      ...state,
      pending_count: staging.total ?? 0,
      accepted_today: 0,
      rejected_today: 0,
      live_photo_pairs: 0,
      last_poll_duration_s: health?.details?.poll_duration_s ?? 0,
      loading: false,
      error: null
    }));
  } catch (error) {
    update((state) => ({ ...state, loading: false, error: error instanceof Error ? error.message : 'Failed to load KPIs' }));
  }
}

export const kpis = { subscribe, load };
