import { describe, expect, it } from 'vitest';

import {
  applyDashboardAccountFilters,
  applyDashboardFilters,
  applyDashboardFileTypeFilters,
  createFilterStore,
  deriveDashboardAccountOptions,
  deriveDashboardFileTypeOptions,
  type DashboardFilterState,
} from '$lib/stores/filterStore';

function readStore(store: { subscribe: (run: (value: DashboardFilterState) => void) => () => void }): DashboardFilterState {
  let snapshot: DashboardFilterState = { activeFilters: [], activeAccounts: new Set<string>() };
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
    expect(readStore(store).activeFilters).toEqual(['jpg']);

    store.toggle('png');
    expect(readStore(store).activeFilters).toEqual(['jpg', 'png']);

    store.toggle('jpg');
    expect(readStore(store).activeFilters).toEqual(['png']);
  });

  it('clears all filters', () => {
    const store = createFilterStore(['jpg', 'mp4'], ['alice']);
    expect(readStore(store).activeFilters).toEqual(['jpg', 'mp4']);
    store.clear();
    expect(readStore(store).activeFilters).toEqual([]);
    expect(Array.from(readStore(store).activeAccounts)).toEqual(['alice']);
  });

  it('toggles accounts on and off and clears account filters', () => {
    const store = createFilterStore([], ['alice']);

    expect(Array.from(readStore(store).activeAccounts)).toEqual(['alice']);

    store.toggleAccount('bob');
    expect(Array.from(readStore(store).activeAccounts).sort()).toEqual(['alice', 'bob']);

    store.toggleAccount('alice');
    expect(Array.from(readStore(store).activeAccounts)).toEqual(['bob']);

    store.clearAccounts();
    expect(Array.from(readStore(store).activeAccounts)).toEqual([]);
  });
});

describe('dashboard file-type filter derivation and application', () => {
  const items = [
    { filename: 'alpha.jpg', sha256: 'a', account: 'alice' },
    { filename: 'beta.JPG', sha256: 'b', account: 'bob' },
    { filename: 'clip.mp4', sha256: 'c', account: 'alice' },
    { filename: 'raw_frame.dng', sha256: 'd', account: null },
    { filename: 'README', sha256: 'e', account: undefined },
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

  it('derives account options with counts and excludes null accounts', () => {
    const options = deriveDashboardAccountOptions(items);
    expect(options.map((opt) => opt.id)).toEqual(['alice', 'bob']);

    const alice = options.find((opt) => opt.id === 'alice');
    const bob = options.find((opt) => opt.id === 'bob');
    expect(alice?.count).toBe(2);
    expect(bob?.count).toBe(1);
  });

  it('applies inclusive OR account filters', () => {
    const filtered = applyDashboardAccountFilters(items, new Set(['alice', 'bob']));
    expect(filtered.map((item) => item.sha256)).toEqual(['a', 'b', 'c']);
  });

  it('combines file-type and account filters with AND across dimensions', () => {
    const filtered = applyDashboardFilters(items, ['jpg'], new Set(['alice']));
    expect(filtered.map((item) => item.sha256)).toEqual(['a']);
  });

  it('returns all items when no filters are active', () => {
    const filtered = applyDashboardFileTypeFilters(items, []);
    expect(filtered).toEqual(items);
  });
});
