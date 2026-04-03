import { apiFetch } from './client';

export function getEffectiveConfig() {
  return apiFetch('/api/v1/config/effective');
}
