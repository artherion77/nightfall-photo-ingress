import { writable } from 'svelte/store';

export interface DashboardFileTypeOption {
  id: string;
  label: string;
  count: number;
  tokenVar: string;
}

export interface DashboardAccountOption {
  id: string;
  label: string;
  count: number;
  tokenVar: string;
}

export interface DashboardFilterState {
  activeFilters: string[];
  activeAccounts: Set<string>;
}

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

export function deriveDashboardAccountOptions(
  items: Array<{ account?: string | null }> = [],
): DashboardAccountOption[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const account = item.account?.trim();
    if (!account) {
      continue;
    }
    counts.set(account, (counts.get(account) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([account, count]) => ({
      id: account,
      label: account,
      count,
      tokenVar: '--filter-type-generic',
    }));
}

export function applyDashboardAccountFilters<T extends { account?: string | null }>(
  items: T[] = [],
  activeAccounts: Set<string> | string[] = new Set<string>(),
): T[] {
  const active = activeAccounts instanceof Set ? activeAccounts : new Set(activeAccounts);
  if (active.size === 0) {
    return items;
  }

  return items.filter((item) => {
    const account = item.account?.trim();
    return !!account && active.has(account);
  });
}

export function applyDashboardFilters<T extends { filename?: string | null; account?: string | null }>(
  items: T[] = [],
  activeFilters: string[] = [],
  activeAccounts: Set<string> | string[] = new Set<string>(),
): T[] {
  const fileTypeFiltered = applyDashboardFileTypeFilters(items, activeFilters);
  return applyDashboardAccountFilters(fileTypeFiltered, activeAccounts);
}

export function createFilterStore(
  initialFilters: string[] = [],
  initialAccounts: Iterable<string> = [],
) {
  const store = writable<DashboardFilterState>({
    activeFilters: initialFilters,
    activeAccounts: new Set(initialAccounts),
  });
  const { subscribe, update, set } = store;

  return {
    subscribe,
    toggle(filterId: string) {
      update((state) => {
        if (state.activeFilters.includes(filterId)) {
          return {
            ...state,
            activeFilters: state.activeFilters.filter((id) => id !== filterId),
          };
        }
        return {
          ...state,
          activeFilters: [...state.activeFilters, filterId],
        };
      });
    },
    toggleAccount(account: string) {
      update((state) => {
        const next = new Set(state.activeAccounts);
        if (next.has(account)) {
          next.delete(account);
        } else {
          next.add(account);
        }
        return {
          ...state,
          activeAccounts: next,
        };
      });
    },
    clear() {
      update((state) => ({
        ...state,
        activeFilters: [],
      }));
    },
    clearAccounts() {
      update((state) => ({
        ...state,
        activeAccounts: new Set<string>(),
      }));
    },
    reset() {
      set({
        activeFilters: [],
        activeAccounts: new Set<string>(),
      });
    },
  };
}
