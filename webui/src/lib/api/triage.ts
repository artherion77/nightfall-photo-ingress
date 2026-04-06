import { apiFetch } from './client';

type TriageAction = 'accept' | 'reject' | 'defer';

interface TriageResponse {
  action_correlation_id: string;
  item_id: string;
  state: string;
}

export function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function postTriage(action: TriageAction, itemId: string, idempotencyKey: string, reason?: string): Promise<TriageResponse> {
  return apiFetch<TriageResponse>(`/api/v1/triage/${encodeURIComponent(itemId)}/${action}`, {
    method: 'POST',
    headers: {
      'X-Idempotency-Key': idempotencyKey
    },
    body: JSON.stringify({ reason: reason ?? null })
  });
}

export function postAccept(itemId: string, idempotencyKey: string, reason?: string) {
  return postTriage('accept', itemId, idempotencyKey, reason);
}

export function postReject(itemId: string, idempotencyKey: string, reason?: string) {
  return postTriage('reject', itemId, idempotencyKey, reason);
}

export function postDefer(itemId: string, idempotencyKey: string, reason?: string) {
  return postTriage('defer', itemId, idempotencyKey, reason);
}
