import { apiFetch } from './client';

export function getStagingPage(cursor?: string | null, limit = 20) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (cursor) {
    params.set('after', cursor);
  }
  return apiFetch(`/api/v1/staging?${params.toString()}`);
}

export function getItem(id: string) {
  return apiFetch(`/api/v1/items/${encodeURIComponent(id)}`);
}
