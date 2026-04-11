import { writable } from 'svelte/store';

export interface DashboardFileTypeOption {
  id: string;
  label: string;
  count: number;
  tokenVar: string;
}

type FilterState = string[];

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'heic', 'heif', 'bmp', 'tif', 'tiff']);
const VIDEO_EXTENSIONS = new Set(['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v']);
const RAW_EXTENSIONS = new Set(['dng', 'raw', 'arw', 'cr2', 'cr3', 'nef', 'orf', 'rw2']);

function normalizeExtension(filename: string | null | undefined): string {
  if (!filename) {
    return 'unknown';
  }
  const trimmed = filename.trim().toLowerCase();
  const dot = trimmed.lastIndexOf('.');
  if (dot <= 0 || dot === trimmed.length - 1) {
    return 'unknown';
  }
  return trimmed.slice(dot + 1);
}

function tokenForExtension(ext: string): string {
  if (IMAGE_EXTENSIONS.has(ext)) {
    return '--filter-type-image';
  }
  if (VIDEO_EXTENSIONS.has(ext)) {
    return '--filter-type-video';
  }
  if (RAW_EXTENSIONS.has(ext)) {
    return '--filter-type-raw';
  }
  return '--filter-type-generic';
}

function labelForExtension(ext: string): string {
  if (ext === 'unknown') {
    return 'Unknown';
  }
  return ext.toUpperCase();
}

export function deriveDashboardFileTypeOptions(
  items: Array<{ filename?: string | null }> = [],
): DashboardFileTypeOption[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const ext = normalizeExtension(item.filename);
    counts.set(ext, (counts.get(ext) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([ext, count]) => ({
      id: ext,
      label: labelForExtension(ext),
      count,
      tokenVar: tokenForExtension(ext),
    }));
}

export function applyDashboardFileTypeFilters<T extends { filename?: string | null }>(
  items: T[] = [],
  activeFilters: string[] = [],
): T[] {
  if (!activeFilters.length) {
    return items;
  }
  const active = new Set(activeFilters);
  return items.filter((item) => active.has(normalizeExtension(item.filename)));
}

export function createFilterStore(initial: FilterState = []) {
  const store = writable<FilterState>(initial);
  const { subscribe, update, set } = store;

  return {
    subscribe,
    toggle(filterId: string) {
      update((state) => {
        if (state.includes(filterId)) {
          return state.filter((id) => id !== filterId);
        }
        return [...state, filterId];
      });
    },
    clear() {
      set([]);
    },
  };
}
