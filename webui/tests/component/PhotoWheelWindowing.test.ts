import { describe, expect, it } from 'vitest';

import {
  getPreloadIndexes,
  getRenderWindow,
  getWindowSlotCounts,
  PRELOAD_RADIUS,
  RENDER_RADIUS,
  shouldRunIdlePreload,
} from '$lib/components/staging/photowheel-windowing';

describe('photowheel windowing helpers', () => {
  it('limits render window to 2*radius+1 nodes in large queues', () => {
    const window = getRenderWindow(25, 60, RENDER_RADIUS);
    const counts = getWindowSlotCounts(window, 60);

    expect(counts.visible).toBe(11);
  });

  it('shifts one slot on next-index navigation', () => {
    const before = getRenderWindow(25, 60, RENDER_RADIUS);
    const after = getRenderWindow(26, 60, RENDER_RADIUS);

    expect(before.start).toBe(20);
    expect(before.end).toBe(30);
    expect(after.start).toBe(21);
    expect(after.end).toBe(31);
  });

  it('computes spacer slot counts to preserve total layout span', () => {
    const window = getRenderWindow(26, 60, RENDER_RADIUS);
    const counts = getWindowSlotCounts(window, 60);

    expect(counts.left).toBe(21);
    expect(counts.visible).toBe(11);
    expect(counts.right).toBe(28);
    expect(counts.left + counts.visible + counts.right).toBe(60);
  });

  it('returns preload neighbors around active index within preload radius', () => {
    const indexes = getPreloadIndexes(10, 30, PRELOAD_RADIUS);
    expect(indexes).toEqual([7, 8, 9, 11, 12, 13]);
  });

  it('gates preload to IDLE settle only', () => {
    expect(shouldRunIdlePreload('IDLE')).toBe(true);
    expect(shouldRunIdlePreload('TRACKING')).toBe(false);
    expect(shouldRunIdlePreload('MOMENTUM')).toBe(false);
    expect(shouldRunIdlePreload('TRANSITIONING')).toBe(false);
  });

  it('renders single item with no spacers', () => {
    const window = getRenderWindow(0, 1);
    const counts = getWindowSlotCounts(window, 1);

    expect(counts.visible).toBe(1);
    expect(counts.left).toBe(0);
    expect(counts.right).toBe(0);
  });

  it('renders all items with no spacers when itemCount < RENDER_RADIUS', () => {
    const window = getRenderWindow(1, 3);
    const counts = getWindowSlotCounts(window, 3);

    expect(counts.visible).toBe(3);
    expect(counts.left).toBe(0);
    expect(counts.right).toBe(0);
  });

  it('returns empty window and zero slots for empty list', () => {
    const window = getRenderWindow(0, 0);
    const counts = getWindowSlotCounts(window, 0);

    expect(counts.visible).toBe(0);
    expect(counts.left).toBe(0);
    expect(counts.right).toBe(0);
  });

  it('returns no preload indexes for empty list', () => {
    expect(getPreloadIndexes(0, 0, PRELOAD_RADIUS)).toEqual([]);
  });

  it('returns only available neighbors when itemCount < PRELOAD_RADIUS', () => {
    // 2 items: only index 1 is a neighbor of index 0
    expect(getPreloadIndexes(0, 2, PRELOAD_RADIUS)).toEqual([1]);
  });
});
