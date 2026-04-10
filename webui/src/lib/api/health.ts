import { apiFetch } from './client';

export interface Subsystem {
  ok: boolean;
  message: string;
}

export interface HealthResponse {
  polling_ok: Subsystem;
  auth_ok: Subsystem;
  registry_ok: Subsystem;
  disk_ok: Subsystem;
  last_updated_at?: string;
  last_poll_at?: string | null;
  next_poll_at?: string | null;
  poller_status?: string;
  poll_interval_minutes?: number;
  error: string | null;
}

export interface PollTriggerResponse {
  status: string;
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/v1/health');
}

export function triggerPoll(): Promise<PollTriggerResponse> {
  return apiFetch<PollTriggerResponse>('/api/v1/poll/trigger', { method: 'POST' });
}
