import { describe, it, expect } from 'vitest';
import { createKPIThresholdsStore } from '$lib/stores/kpiThresholds.svelte.js';

describe('KPIThresholdsStore', () => {
  describe('Initial state', () => {
    it('should have default thresholds on creation', () => {
      const store = createKPIThresholdsStore();
      let state: any;

      const unsubscribe = store.subscribe((value: any) => {
        state = value;
      });

      expect(state).toBeDefined();
      expect(state.thresholds).toEqual({
        pending_warning: 100,
        pending_error: 500,
        disk_warning_percent: 80,
        disk_error_percent: 95,
      });
      expect(state.loading).toBe(false);
      expect(state.saving).toBe(false);
      expect(state.error).toBeNull();
      expect(state.success).toBe(false);

      unsubscribe();
    });

    it('should initialize with null updated_at', () => {
      const store = createKPIThresholdsStore();
      let state: any;

      const unsubscribe = store.subscribe((value: any) => {
        state = value;
      });

      expect(state.updated_at).toBeNull();

      unsubscribe();
    });

    it('should have working subscribe/unsubscribe', () => {
      const store = createKPIThresholdsStore();
      let callCount = 0;

      const unsubscribe = store.subscribe(() => {
        callCount++;
      });

      expect(callCount).toBe(1); // Called once on subscription

      unsubscribe();
      expect(callCount).toBe(1); // Not called after unsubscribe
    });
  });
});
