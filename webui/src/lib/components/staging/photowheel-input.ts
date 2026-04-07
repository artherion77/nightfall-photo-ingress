export const WHEEL_THRESHOLD_PX = 60;
export const TOUCH_DEAD_ZONE_PX = 10;
export const TOUCH_COMMIT_PX = 40;
export const TOUCH_FLING_PX_PER_MS = 0.3;

export interface WheelResult {
  step: number;
  accumulator: number;
}

export interface TouchState {
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
  velocityX: number;
  lastTs: number;
  trackingSwipe: boolean;
}

export interface TouchRelease {
  step: number;
  momentumVelocityPxPerMs: number;
}

export function clampIndex(index: number, itemCount: number): number {
  if (itemCount <= 0) return 0;
  return Math.max(0, Math.min(index, itemCount - 1));
}

export function computeWheelStep(
  deltaY: number,
  deltaMode: number,
  accumulator: number,
  thresholdPx: number = WHEEL_THRESHOLD_PX
): WheelResult {
  // DOM_DELTA_LINE means detent-like wheel behavior.
  if (deltaMode === 1 || Math.abs(deltaY) >= thresholdPx) {
    return {
      step: deltaY > 0 ? 1 : -1,
      accumulator: 0,
    };
  }

  const nextAccumulator = accumulator + deltaY;
  if (Math.abs(nextAccumulator) < thresholdPx) {
    return {
      step: 0,
      accumulator: nextAccumulator,
    };
  }

  return {
    step: nextAccumulator > 0 ? 1 : -1,
    accumulator: 0,
  };
}

export function shouldPreventWheelScroll(
  activeIndex: number,
  itemCount: number,
  deltaY: number
): boolean {
  if (itemCount <= 0) return false;

  const atFirst = activeIndex <= 0;
  const atLast = activeIndex >= itemCount - 1;

  if (atFirst && deltaY < 0) return false;
  if (atLast && deltaY > 0) return false;
  return true;
}

export function startTouch(x: number, y: number, ts: number): TouchState {
  return {
    startX: x,
    startY: y,
    currentX: x,
    currentY: y,
    velocityX: 0,
    lastTs: ts,
    trackingSwipe: false,
  };
}

export function updateTouch(
  state: TouchState,
  x: number,
  y: number,
  ts: number,
  deadZonePx: number = TOUCH_DEAD_ZONE_PX
): TouchState {
  const dt = Math.max(1, ts - state.lastTs);
  const dxInstant = x - state.currentX;
  const velocityX = dxInstant / dt;

  const nextDx = x - state.startX;
  const nextDy = y - state.startY;
  const trackingSwipe =
    state.trackingSwipe || (Math.abs(nextDx) > deadZonePx && Math.abs(nextDx) > Math.abs(nextDy));

  return {
    ...state,
    currentX: x,
    currentY: y,
    velocityX,
    lastTs: ts,
    trackingSwipe,
  };
}

export function resolveTouchStep(
  state: TouchState,
  commitPx: number = TOUCH_COMMIT_PX,
  flingPxPerMs: number = TOUCH_FLING_PX_PER_MS
): number {
  return resolveTouchRelease(state, commitPx, flingPxPerMs).step;
}

export function resolveTouchRelease(
  state: TouchState,
  commitPx: number = TOUCH_COMMIT_PX,
  flingPxPerMs: number = TOUCH_FLING_PX_PER_MS
): TouchRelease {
  const dxTotal = state.currentX - state.startX;
  if (!state.trackingSwipe) {
    return {
      step: 0,
      momentumVelocityPxPerMs: 0,
    };
  }

  // Convert X-axis gesture velocity into wheel step direction.
  const momentumVelocityPxPerMs = -state.velocityX;

  if (Math.abs(dxTotal) >= commitPx || Math.abs(state.velocityX) >= flingPxPerMs) {
    // Swipe left advances to next item, swipe right goes to previous item.
    return {
      step: dxTotal < 0 ? 1 : -1,
      momentumVelocityPxPerMs,
    };
  }

  return {
    step: 0,
    momentumVelocityPxPerMs,
  };
}