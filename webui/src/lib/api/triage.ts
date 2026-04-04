import { apiFetch } from './client';

type TriageAction = 'accept' | 'reject' | 'defer';

interface TriageResponse {
  action_correlation_id: string;
  item_id: string;
  state: string;
}

function buildIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function postTriage(action: TriageAction, itemId: string, reason?: string): Promise<TriageResponse> {
  return apiFetch<TriageResponse>(`/api/v1/triage/${encodeURIComponent(itemId)}/${action}`, {
    method: 'POST',
    headers: {
      'X-Idempotency-Key': buildIdempotencyKey()
    },
    body: JSON.stringify({ reason: reason ?? null })
  });
}

export function postAccept(itemId: string, reason?: string) {
  return postTriage('accept', itemId, reason);
}

export function postReject(itemId: string, reason?: string) {
  return postTriage('reject', itemId, reason);
}

export function postDefer(itemId: string, reason?: string) {
  return postTriage('defer', itemId, reason);
}
