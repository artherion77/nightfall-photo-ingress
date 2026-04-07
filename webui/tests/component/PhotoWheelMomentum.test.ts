import { describe, expect, it } from 'vitest';

import {
  MOMENTUM_FRICTION,
  MOMENTUM_MIN_VELOCITY_PX_PER_MS,
  shouldCancelMotionOnInput,
  shouldStartMomentum,
  stepMomentumFrame,
} from '$lib/components/staging/photowheel-momentum';

describe('photowheel momentum helpers', () => {
  it('starts momentum when release velocity exceeds fling threshold', () => {
    expect(shouldStartMomentum(0.31, 0.3)).toBe(true);
    expect(shouldStartMomentum(-0.31, 0.3)).toBe(true);
    expect(shouldStartMomentum(0.2, 0.3)).toBe(false);
  });

  it('decays velocity by friction coefficient each frame', () => {
    const result = stepMomentumFrame({
      activeIndex: 5,
      itemCount: 12,
      velocityPxPerMs: 0.5,
      accumulatorPx: 0,
      dtMs: 16,
    });

    expect(result.velocityPxPerMs).toBeCloseTo(0.5 * MOMENTUM_FRICTION, 6);
    expect(result.state).toBe('MOMENTUM');
  });

  it('advances one step when accumulated displacement crosses threshold', () => {
    const result = stepMomentumFrame({
      activeIndex: 3,
      itemCount: 12,
      velocityPxPerMs: 5,
      accumulatorPx: 59,
      dtMs: 1,
      friction: 1,
      stepThresholdPx: 60,
    });

    expect(result.activeIndex).toBe(4);
    expect(result.state).toBe('MOMENTUM');
  });

  it('terminates momentum when velocity drops below minimum threshold', () => {
    const result = stepMomentumFrame({
      activeIndex: 2,
      itemCount: 12,
      velocityPxPerMs: MOMENTUM_MIN_VELOCITY_PX_PER_MS,
      accumulatorPx: 0,
      dtMs: 16,
    });

    expect(result.state).toBe('IDLE');
    expect(result.velocityPxPerMs).toBe(0);
  });

  it('terminates momentum at queue boundaries', () => {
    const result = stepMomentumFrame({
      activeIndex: 11,
      itemCount: 12,
      velocityPxPerMs: 4,
      accumulatorPx: 80,
      dtMs: 16,
      friction: 1,
      stepThresholdPx: 60,
    });

    expect(result.state).toBe('IDLE');
    expect(result.cancelledByBoundary).toBe(true);
    expect(result.activeIndex).toBe(11);
  });

  it('cancels motion only in transitioning or momentum state', () => {
    expect(shouldCancelMotionOnInput('IDLE')).toBe(false);
    expect(shouldCancelMotionOnInput('STEP')).toBe(false);
    expect(shouldCancelMotionOnInput('TRACKING')).toBe(false);
    expect(shouldCancelMotionOnInput('TRANSITIONING')).toBe(true);
    expect(shouldCancelMotionOnInput('MOMENTUM')).toBe(true);
  });
});
