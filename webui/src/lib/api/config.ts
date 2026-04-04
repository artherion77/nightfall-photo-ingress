import { apiFetch } from './client';

export interface EffectiveConfig {
  kpi_thresholds?: Record<string, number>;
  [key: string]: unknown;
}

export function getEffectiveConfig(): Promise<EffectiveConfig> {
  return apiFetch<EffectiveConfig>('/api/v1/config/effective');
}
