import { apiFetch } from './client';

export function getAuditLog(cursor?: string | null, limit = 50, action?: string | null) {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (cursor) {
    params.set('after', cursor);
  }
  if (action) {
    params.set('action', action);
  }
  return apiFetch(`/api/v1/audit-log?${params.toString()}`);
}
