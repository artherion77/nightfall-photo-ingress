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
  error: string | null;
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/v1/health');
}
