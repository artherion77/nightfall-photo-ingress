import { clampIndex } from './photowheel-input';

export const MOMENTUM_FRICTION = 0.92;
export const MOMENTUM_MIN_VELOCITY_PX_PER_MS = 0.05;
export const MOMENTUM_STEP_THRESHOLD_PX = 60;

export type ActiveIndexState = 'IDLE' | 'STEP' | 'TRACKING' | 'TRANSITIONING' | 'MOMENTUM';

export interface MomentumFrameInput {
  activeIndex: number;
  itemCount: number;
  velocityPxPerMs: number;
  accumulatorPx: number;
  dtMs: number;
  friction?: number;
  minVelocityPxPerMs?: number;
  stepThresholdPx?: number;
}

export interface MomentumFrameResult {
  activeIndex: number;
  velocityPxPerMs: number;
  accumulatorPx: number;
  state: ActiveIndexState;
  cancelledByBoundary: boolean;
}

export function shouldCancelMotionOnInput(state: ActiveIndexState): boolean {
  return state === 'TRANSITIONING' || state === 'MOMENTUM';
}

export function shouldStartMomentum(
  releaseVelocityPxPerMs: number,
  flingThresholdPxPerMs: number
): boolean {
  return Math.abs(releaseVelocityPxPerMs) >= flingThresholdPxPerMs;
}

export function stepMomentumFrame(input: MomentumFrameInput): MomentumFrameResult {
  const friction = input.friction ?? MOMENTUM_FRICTION;
  const minVelocity = input.minVelocityPxPerMs ?? MOMENTUM_MIN_VELOCITY_PX_PER_MS;
  const stepThreshold = input.stepThresholdPx ?? MOMENTUM_STEP_THRESHOLD_PX;

  if (input.itemCount <= 0) {
    return {
      activeIndex: 0,
      velocityPxPerMs: 0,
      accumulatorPx: 0,
      state: 'IDLE',
      cancelledByBoundary: false,
    };
  }

  let velocity = input.velocityPxPerMs * friction;
  if (Math.abs(velocity) < minVelocity) {
    return {
      activeIndex: input.activeIndex,
      velocityPxPerMs: 0,
      accumulatorPx: 0,
      state: 'IDLE',
      cancelledByBoundary: false,
    };
  }

  let accumulator = input.accumulatorPx + velocity * input.dtMs;
  let nextIndex = input.activeIndex;

  while (Math.abs(accumulator) >= stepThreshold) {
    const direction = accumulator > 0 ? 1 : -1;
    const bounded = clampIndex(nextIndex + direction, input.itemCount);

    if (bounded === nextIndex) {
      return {
        activeIndex: nextIndex,
        velocityPxPerMs: 0,
        accumulatorPx: 0,
        state: 'IDLE',
        cancelledByBoundary: true,
      };
    }

    nextIndex = bounded;
    accumulator -= direction * stepThreshold;
  }

  return {
    activeIndex: nextIndex,
    velocityPxPerMs: velocity,
    accumulatorPx: accumulator,
    state: 'MOMENTUM',
    cancelledByBoundary: false,
  };
}
