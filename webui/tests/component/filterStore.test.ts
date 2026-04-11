import { describe, expect, it } from 'vitest';

import {
  applyDashboardFileTypeFilters,
  createFilterStore,
  deriveDashboardFileTypeOptions,
} from '$lib/stores/filterStore';

function readStore(store: { subscribe: (run: (value: string[]) => void) => () => void }): string[] {
  let snapshot: string[] = [];
  const unsubscribe = store.subscribe((value) => {
    snapshot = value;
  });
  unsubscribe();
  return snapshot;
}

describe('filterStore transitions', () => {
  it('toggles filter ids on and off', () => {
    const store = createFilterStore();

    store.toggle('jpg');
    expect(readStore(store)).toEqual(['jpg']);

    store.toggle('png');
    expect(readStore(store)).toEqual(['jpg', 'png']);

    store.toggle('jpg');
    expect(readStore(store)).toEqual(['png']);
  });

  it('clears all filters', () => {
    const store = createFilterStore(['jpg', 'mp4']);
    expect(readStore(store)).toEqual(['jpg', 'mp4']);
    store.clear();
    expect(readStore(store)).toEqual([]);
  });
});

describe('dashboard file-type filter derivation and application', () => {
  const items = [
    { filename: 'alpha.jpg', sha256: 'a' },
    { filename: 'beta.JPG', sha256: 'b' },
    { filename: 'clip.mp4', sha256: 'c' },
    { filename: 'raw_frame.dng', sha256: 'd' },
    { filename: 'README', sha256: 'e' },
  ];

  it('derives unique options with counts and token mappings', () => {
    const options = deriveDashboardFileTypeOptions(items);
    expect(options.map((opt) => opt.id)).toEqual(['dng', 'jpg', 'mp4', 'unknown']);

    const jpg = options.find((opt) => opt.id === 'jpg');
    const mp4 = options.find((opt) => opt.id === 'mp4');
    const dng = options.find((opt) => opt.id === 'dng');
    const unknown = options.find((opt) => opt.id === 'unknown');

    expect(jpg?.count).toBe(2);
    expect(jpg?.tokenVar).toBe('--filter-type-image');
    expect(mp4?.tokenVar).toBe('--filter-type-video');
    expect(dng?.tokenVar).toBe('--filter-type-raw');
    expect(unknown?.tokenVar).toBe('--filter-type-generic');
  });

  it('applies multiple active filters client-side', () => {
    const filtered = applyDashboardFileTypeFilters(items, ['jpg', 'mp4']);
    expect(filtered.map((item) => item.sha256)).toEqual(['a', 'b', 'c']);
  });

  it('returns all items when no filters are active', () => {
    const filtered = applyDashboardFileTypeFilters(items, []);
    expect(filtered).toEqual(items);
  });
});
