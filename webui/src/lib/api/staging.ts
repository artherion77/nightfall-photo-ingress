import { apiFetch } from './client';

export interface StagingItem {
  item_id: string;
  filename: string;
  sha256: string;
  first_seen_at: string;
  account: string;
  status: string;
}

export interface StagingPage {
  items: StagingItem[];
  total: number;
  cursor: string | null;
}

export function getStagingPage(cursor?: string | null, limit = 20): Promise<StagingPage> {
  const params = new URLSearchParams();
  params.set('limit', String(limit));
  if (cursor) {
    params.set('after', cursor);
  }
  return apiFetch<StagingPage>(`/api/v1/staging?${params.toString()}`);
}

export function getItem(id: string): Promise<StagingItem> {
  return apiFetch<StagingItem>(`/api/v1/items/${encodeURIComponent(id)}`);
}
