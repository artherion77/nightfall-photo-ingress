import { writable } from 'svelte/store';

interface HealthState {
  polling_ok: boolean;
  auth_ok: boolean;
  registry_ok: boolean;
  disk_ok: boolean;
  last_updated_at?: string;
  error: string | null;
}

const initialState: HealthState = {
  polling_ok: false,
  auth_ok: false,
  registry_ok: false,
  disk_ok: false,
  error: null
};

const { subscribe, set, update } = writable(initialState);

let pollingInterval: number | null = null;

async function fetchHealth() {
  try {
    const response = await fetch('/api/v1/health', {
      headers: {
        'Authorization': `Bearer ${import.meta.env.PUBLIC_API_TOKEN}`
      }
    });

    if (response.ok) {
      const data = await response.json();
      update(() => ({
        polling_ok: data.polling_ok ?? false,
        auth_ok: data.auth_ok ?? false,
        registry_ok: data.registry_ok ?? false,
        disk_ok: data.disk_ok ?? false,
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
});
