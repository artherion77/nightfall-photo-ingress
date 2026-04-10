import { writable } from 'svelte/store';
import { getHealth, triggerPoll as triggerPollApi } from '$lib/api/health';
import { ApiError } from '$lib/api/client';

const initialState = {
  polling_ok: { ok: false, message: 'unknown' },
  auth_ok: { ok: false, message: 'unknown' },
  registry_ok: { ok: false, message: 'unknown' },
  disk_ok: { ok: false, message: 'unknown' },
  last_updated_at: /** @type {string | undefined} */ (undefined),
  last_poll_at: /** @type {string | null | undefined} */ (undefined),
  next_poll_at: /** @type {string | null} */ (null),
  poller_status: /** @type {string} */ ('unknown'),
  poll_interval_minutes: /** @type {number} */ (0),
  error: null
};

const { subscribe, update } = writable(initialState);

let pollingInterval = null;
let consecutiveFailures = 0;
const FAILURE_THRESHOLD = 3;

async function fetchHealth() {
  try {
    const data = await getHealth();
    consecutiveFailures = 0;
    update((state) => ({
      ...state,
      polling_ok: data.polling_ok ?? initialState.polling_ok,
      auth_ok: data.auth_ok ?? initialState.auth_ok,
      registry_ok: data.registry_ok ?? initialState.registry_ok,
      disk_ok: data.disk_ok ?? initialState.disk_ok,
      last_updated_at: data.last_updated_at,
      last_poll_at: data.last_poll_at ?? null,
      next_poll_at: data.next_poll_at ?? null,
      poller_status: data.poller_status ?? 'unknown',
      poll_interval_minutes: data.poll_interval_minutes ?? 0,
      error: null
    }));
  } catch (err) {
    consecutiveFailures++;
    if (consecutiveFailures >= FAILURE_THRESHOLD) {
      const msg =
        err instanceof ApiError ? `API error: ${err.status}` : 'Health check failed';
      update((state) => ({ ...state, error: msg }));
    }
    // Silently swallow failures below threshold (transient errors after retry exhaustion)
  }
}

async function triggerPoll() {
  try {
    await triggerPollApi();
    await fetchHealth();
  } finally {
    // fetchHealth already settled; nothing extra needed
  }
}

function connect() {
  // Fetch immediately
  fetchHealth();
  
  // Then poll every 30 seconds
  if (typeof window !== 'undefined') {
    pollingInterval = window.setInterval(fetchHealth, 30000);
  }
}

function disconnect() {
  if (pollingInterval !== null) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}

export const health = {
  subscribe,
  connect,
  disconnect,
  triggerPoll,
  ...initialState
};

// Update store to be reactive to health state changes
subscribe((state) => {
  Object.assign(health, state);
  health.polling_ok_flag = Boolean(state.polling_ok?.ok);
  health.auth_ok_flag = Boolean(state.auth_ok?.ok);
  health.registry_ok_flag = Boolean(state.registry_ok?.ok);
  health.disk_ok_flag = Boolean(state.disk_ok?.ok);
});
