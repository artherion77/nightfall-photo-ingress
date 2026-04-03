import { writable } from 'svelte/store';
import { PUBLIC_API_TOKEN } from '$env/static/public';

const initialState = {
  polling_ok: { ok: false, message: 'unknown' },
  auth_ok: { ok: false, message: 'unknown' },
  registry_ok: { ok: false, message: 'unknown' },
  disk_ok: { ok: false, message: 'unknown' },
  error: null
};

const { subscribe, update } = writable(initialState);

let pollingInterval = null;

async function fetchHealth() {
  try {
    const response = await fetch('/api/v1/health', {
      headers: {
        'Authorization': `Bearer ${PUBLIC_API_TOKEN}`
      }
    });

    if (response.ok) {
      const data = await response.json();
      update(() => ({
        polling_ok: data.polling_ok ?? initialState.polling_ok,
        auth_ok: data.auth_ok ?? initialState.auth_ok,
        registry_ok: data.registry_ok ?? initialState.registry_ok,
        disk_ok: data.disk_ok ?? initialState.disk_ok,
        last_updated_at: data.last_updated_at,
        error: data.error || null
      }));
    } else {
      update((state) => ({
        ...state,
        error:  `API error: ${response.status}`
      }));
    }
  } catch (err) {
    update((state) => ({
      ...state,
      error: 'Failed to fetch health status'
    }));
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
