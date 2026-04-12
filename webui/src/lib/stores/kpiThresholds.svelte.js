// Svelte store for KPI threshold settings state management.

import { writable } from 'svelte/store';

export function createKPIThresholdsStore() {
  const { subscribe, set, update } = writable({
    thresholds: {
      pending_warning: 100,
      pending_error: 500,
      disk_warning_percent: 80,
      disk_error_percent: 95,
    },
    loading: false,
    saving: false,
    error: null,
    success: false,
    updated_at: null,
  });

  return {
    subscribe,

    async load() {
      update(state => ({ ...state, loading: true, error: null }));
      try {
        const response = await fetch('/api/v1/settings/kpi-thresholds', {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${getApiToken()}`,
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to load KPI thresholds: ${response.statusText}`);
        }

        const data = await response.json();
        update(state => ({
          ...state,
          thresholds: data.thresholds,
          updated_at: data.updated_at,
          loading: false,
        }));
      } catch (error) {
        update(state => ({
          ...state,
          error: error instanceof Error ? error.message : String(error),
          loading: false,
        }));
      }
    },

    async update(thresholds) {
      update(state => ({
        ...state,
        saving: true,
        error: null,
        success: false,
      }));

      try {
        const response = await fetch('/api/v1/settings/kpi-thresholds', {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${getApiToken()}`,
          },
          body: JSON.stringify(thresholds),
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(
            errorData.detail || `Failed to update thresholds: ${response.statusText}`
          );
        }

        const data = await response.json();
        update(state => ({
          ...state,
          thresholds: data.thresholds,
          updated_at: data.updated_at,
          saving: false,
          success: true,
        }));

        // Clear success message after 5 seconds
        setTimeout(() => {
          update(state => ({ ...state, success: false }));
        }, 5000);
      } catch (error) {
        update(state => ({
          ...state,
          error: error instanceof Error ? error.message : String(error),
          saving: false,
        }));
      }
    },

    async reset() {
      update(state => ({
        ...state,
        saving: true,
        error: null,
        success: false,
      }));

      try {
        const response = await fetch('/api/v1/settings/kpi-thresholds', {
          method: 'DELETE',
          headers: {
            Authorization: `Bearer ${getApiToken()}`,
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to reset thresholds: ${response.statusText}`);
        }

        const data = await response.json();
        update(state => ({
          ...state,
          thresholds: data.thresholds,
          updated_at: data.updated_at,
          saving: false,
          success: true,
        }));

        // Clear success message after 5 seconds
        setTimeout(() => {
          update(state => ({ ...state, success: false }));
        }, 5000);
      } catch (error) {
        update(state => ({
          ...state,
          error: error instanceof Error ? error.message : String(error),
          saving: false,
        }));
      }
    },

    clearError() {
      update(state => ({ ...state, error: null }));
    },

    clearSuccess() {
      update(state => ({ ...state, success: false }));
    },
  };
}

function getApiToken() {
  // In a real app, this would come from auth state
  // For now, assume it's available from a global or auth context
  return localStorage.getItem('api_token') || '';
}

export const kpiThresholds = createKPIThresholdsStore();
