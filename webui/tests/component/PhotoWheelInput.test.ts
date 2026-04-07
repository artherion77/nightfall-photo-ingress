import { describe, expect, it } from 'vitest';

import {
  clampIndex,
  computeWheelStep,
  resolveTouchRelease,
  resolveTouchStep,
  shouldPreventWheelScroll,
  startTouch,
  updateTouch,
} from '$lib/components/staging/photowheel-input';

describe('photowheel input helpers', () => {
  it('clamps index boundaries', () => {
    expect(clampIndex(-1, 5)).toBe(0);
    expect(clampIndex(10, 5)).toBe(4);
    expect(clampIndex(2, 5)).toBe(2);
    expect(clampIndex(2, 0)).toBe(0);
  });

  it('classifies detent wheel step', () => {
    const result = computeWheelStep(120, 1, 0);
    expect(result.step).toBe(1);
    expect(result.accumulator).toBe(0);
  });

  it('accumulates continuous wheel delta until threshold', () => {
    const first = computeWheelStep(20, 0, 0, 60);
    expect(first.step).toBe(0);
    expect(first.accumulator).toBe(20);

    const second = computeWheelStep(20, 0, first.accumulator, 60);
    expect(second.step).toBe(0);
    expect(second.accumulator).toBe(40);

    const third = computeWheelStep(25, 0, second.accumulator, 60);
    expect(third.step).toBe(1);
    expect(third.accumulator).toBe(0);
  });

  it('releases scroll lock when boundary overflow direction is requested', () => {
    expect(shouldPreventWheelScroll(0, 5, -40)).toBe(false);
    expect(shouldPreventWheelScroll(4, 5, 40)).toBe(false);
    expect(shouldPreventWheelScroll(2, 5, 40)).toBe(true);
  });

  it('tracks touch swipe and resolves commit by distance', () => {
    const start = startTouch(100, 200, 1000);
    const move = updateTouch(start, 40, 205, 1100, 10);

    expect(move.trackingSwipe).toBe(true);
    expect(resolveTouchStep(move, 40, 0.3)).toBe(1);
  });

  it('resolves touch fling by velocity', () => {
    const start = startTouch(100, 200, 1000);
    const move = updateTouch(start, 88, 200, 1001, 10);

    // Dead-zone crossing with very high instantaneous velocity triggers fling.
    expect(resolveTouchStep(move, 40, 0.3)).toBe(1);
  });

  it('returns release velocity for momentum handoff', () => {
    const start = startTouch(100, 200, 1000);
    const move = updateTouch(start, 60, 200, 1020, 10);

    const release = resolveTouchRelease(move, 40, 0.3);
    expect(release.step).toBe(1);
    expect(release.momentumVelocityPxPerMs).toBeGreaterThan(0);
  });

  it('does not commit below dead zone and without fling', () => {
    const start = startTouch(100, 200, 1000);
    const move = updateTouch(start, 104, 205, 1100, 10);

    expect(move.trackingSwipe).toBe(false);
    expect(resolveTouchStep(move, 40, 0.3)).toBe(0);
  });
});
