import { apiFetch } from './client';

export function getBlocklist() {
  return apiFetch('/api/v1/blocklist');
}

export interface BlockRulePayload {
  pattern?: string;
  rule_type?: 'filename' | 'regex';
  reason?: string | null;
  enabled?: boolean;
}

export function createRule(body: BlockRulePayload, idempotencyKey: string) {
  return apiFetch('/api/v1/blocklist', {
    method: 'POST',
    headers: {
      'X-Idempotency-Key': idempotencyKey
    },
    body: JSON.stringify(body)
  });
}

export function updateRule(id: number, body: BlockRulePayload, idempotencyKey: string) {
  return apiFetch(`/api/v1/blocklist/${id}`, {
    method: 'PATCH',
    headers: {
      'X-Idempotency-Key': idempotencyKey
    },
    body: JSON.stringify(body)
  });
}

export function deleteRule(id: number, idempotencyKey: string) {
  return apiFetch(`/api/v1/blocklist/${id}`, {
    method: 'DELETE',
    headers: {
      'X-Idempotency-Key': idempotencyKey
    }
  });
}
