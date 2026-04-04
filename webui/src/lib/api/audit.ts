import { apiFetch } from './client';

export interface AuditEvent {
  id: number;
  action: string;
  ts: string;
  actor: string;
  sha256?: string;
  account_name?: string;
  reason?: string;
  details?: Record<string, unknown>;
}

export interface AuditPage {
  events: AuditEvent[];
  cursor: string | null;
  has_more: boolean;
}

export function getAuditLog(cursor?: string | null, limit = 50, action?: string | null): Promise<AuditPage> {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (cursor) {
    params.set('after', cursor);
  }
  if (action) {
    params.set('action', action);
  }
  return apiFetch<AuditPage>(`/api/v1/audit-log?${params.toString()}`);
}
