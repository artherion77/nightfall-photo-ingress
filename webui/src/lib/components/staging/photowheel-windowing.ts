import { clampIndex } from './photowheel-input';
import type { ActiveIndexState } from './photowheel-momentum';

export const RENDER_RADIUS = 5;
export const PRELOAD_RADIUS = 3;

export interface RenderWindow {
  start: number;
  end: number;
}

export interface WindowSlotCounts {
  left: number;
  visible: number;
  right: number;
}

export function getRenderWindow(
  activeIndex: number,
  itemCount: number,
  radius: number = RENDER_RADIUS
): RenderWindow {
  if (itemCount <= 0) {
    return {
      start: 0,
      end: -1,
    };
  }

  const clamped = clampIndex(activeIndex, itemCount);
  return {
    start: Math.max(0, clamped - radius),
    end: Math.min(itemCount - 1, clamped + radius),
  };
}

export function getWindowSlotCounts(window: RenderWindow, itemCount: number): WindowSlotCounts {
  if (itemCount <= 0 || window.end < window.start) {
    return {
      left: 0,
      visible: 0,
      right: 0,
    };
  }

  const left = window.start;
  const visible = window.end - window.start + 1;
  const right = Math.max(itemCount - window.end - 1, 0);

  return {
    left,
    visible,
    right,
  };
}

export function shouldRunIdlePreload(state: ActiveIndexState): boolean {
  return state === 'IDLE';
}

export function getPreloadIndexes(
  activeIndex: number,
  itemCount: number,
  preloadRadius: number = PRELOAD_RADIUS
): number[] {
  if (itemCount <= 0) return [];

  const clamped = clampIndex(activeIndex, itemCount);
  const indexes: number[] = [];

  const start = Math.max(0, clamped - preloadRadius);
  const end = Math.min(itemCount - 1, clamped + preloadRadius);

  for (let i = start; i <= end; i += 1) {
    if (i !== clamped) {
      indexes.push(i);
    }
  }

  return indexes;
}
