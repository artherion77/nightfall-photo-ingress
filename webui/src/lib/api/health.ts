import { apiFetch } from './client';

export function getHealth() {
  return apiFetch('/api/v1/health');
}
