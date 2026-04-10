import { apiFetch } from './client';

export interface AuditEvent {
  id: number;
  action: string;
  description: string;
  ts: string;
  actor: string;
  sha256?: string | null;
  account_name?: string;
  filename?: string | null;
  reason?: string;
  details?: Record<string, unknown>;
}

export interface AuditPage {
  events: AuditEvent[];
  cursor: string | null;
  has_more: boolean;
}

export interface AuditDailySummary {
  day_utc: string;
  accepted_today: number;
  rejected_today: number;
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

export function getAuditDailySummary(): Promise<AuditDailySummary> {
  return apiFetch<AuditDailySummary>('/api/v1/audit-log/daily-summary');
}
