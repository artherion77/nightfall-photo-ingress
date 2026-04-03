import { apiFetch } from './client';

export function getBlocklist() {
  return apiFetch('/api/v1/blocklist');
}
