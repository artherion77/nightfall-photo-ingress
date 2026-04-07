<script lang="ts">
  import { onDestroy } from 'svelte';
  import EmptyState from '$lib/components/common/EmptyState.svelte';
  import PhotoCard from './PhotoCard.svelte';
  import {
    clampIndex,
    computeWheelStep,
    resolveTouchRelease,
    shouldPreventWheelScroll,
    startTouch,
    updateTouch,
    TOUCH_FLING_PX_PER_MS,
    type TouchState,
  } from './photowheel-input';
  import {
    shouldCancelMotionOnInput,
    shouldStartMomentum,
    stepMomentumFrame,
    type ActiveIndexState,
  } from './photowheel-momentum';
  import {
    getPreloadIndexes,
    getRenderWindow,
    getWindowSlotCounts,
    PRELOAD_RADIUS,
    RENDER_RADIUS,
    shouldRunIdlePreload,
  } from './photowheel-windowing';

  interface Item {
    sha256: string;
    filename: string;
    account?: string;
    first_seen_at?: string;
  }

  interface Props {
    items: Item[];
    activeIndex?: number;
    onSelect?: (index: number) => void;
    onAccept?: () => void;
    onReject?: () => void;
    onDefer?: () => void;
  }

  let { items, activeIndex = 0, onSelect, onAccept, onReject, onDefer }: Props = $props();

  let wheelAccumulator = 0;
  let lastWheelTs = 0;
  let hasPointerFocus = false;
  let touchState: TouchState | null = null;
  let interactionState = $state<ActiveIndexState>('IDLE');
  let momentumVelocityPxPerMs = 0;
  let momentumAccumulatorPx = 0;
  let momentumFrameId: number | null = null;
  let lastMomentumFrameTs = 0;
  let momentumActiveIndex: number | null = null;
  let transitionTimer: ReturnType<typeof setTimeout> | null = null;
  let preloadedImages: HTMLImageElement[] = [];

  const TRANSITION_SETTLE_MS = 220;

  function clearTransitionTimer(): void {
    if (!transitionTimer) return;
    clearTimeout(transitionTimer);
    transitionTimer = null;
  }

  function scheduleTransitionToIdle(): void {
    clearTransitionTimer();
    interactionState = 'TRANSITIONING';
    transitionTimer = setTimeout(() => {
      if (interactionState === 'TRANSITIONING') {
        interactionState = 'IDLE';
      }
    }, TRANSITION_SETTLE_MS);
  }

  function cancelMotion(): void {
    if (momentumFrameId !== null) {
      cancelAnimationFrame(momentumFrameId);
      momentumFrameId = null;
    }
    momentumVelocityPxPerMs = 0;
    momentumAccumulatorPx = 0;
    lastMomentumFrameTs = 0;
    momentumActiveIndex = null;
    clearTransitionTimer();
    interactionState = 'IDLE';
  }

  function cancelMotionOnNewInput(): void {
    if (shouldCancelMotionOnInput(interactionState)) {
      cancelMotion();
    }
  }

  function runMomentumFrame(ts: number): void {
    if (interactionState !== 'MOMENTUM') {
      momentumFrameId = null;
      return;
    }

    if (lastMomentumFrameTs === 0) {
      lastMomentumFrameTs = ts;
      momentumFrameId = requestAnimationFrame(runMomentumFrame);
      return;
    }

    const dtMs = Math.max(1, ts - lastMomentumFrameTs);
    lastMomentumFrameTs = ts;

    const frame = stepMomentumFrame({
      activeIndex: momentumActiveIndex ?? activeIndex,
      itemCount: items.length,
      velocityPxPerMs: momentumVelocityPxPerMs,
      accumulatorPx: momentumAccumulatorPx,
      dtMs,
    });

    momentumVelocityPxPerMs = frame.velocityPxPerMs;
    momentumAccumulatorPx = frame.accumulatorPx;
    momentumActiveIndex = frame.activeIndex;

    if (frame.activeIndex !== activeIndex) {
      onSelect?.(frame.activeIndex);
    }

    if (frame.state === 'IDLE') {
      cancelMotion();
      return;
    }

    momentumFrameId = requestAnimationFrame(runMomentumFrame);
  }

  function startMomentum(initialVelocityPxPerMs: number): void {
    if (items.length === 0) return;
    if (!shouldStartMomentum(initialVelocityPxPerMs, TOUCH_FLING_PX_PER_MS)) return;

    clearTransitionTimer();
    interactionState = 'MOMENTUM';
    momentumVelocityPxPerMs = initialVelocityPxPerMs;
    momentumAccumulatorPx = 0;
    momentumActiveIndex = activeIndex;
    lastMomentumFrameTs = 0;

    if (momentumFrameId !== null) {
      cancelAnimationFrame(momentumFrameId);
    }
    momentumFrameId = requestAnimationFrame(runMomentumFrame);
  }

  function handleKeydown(event: KeyboardEvent): void {
    cancelMotionOnNewInput();

    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      selectDelta(-1, 'STEP');
      return;
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault();
      selectDelta(1, 'STEP');
      return;
    }

    if (event.key.toLowerCase() === 'a') {
      event.preventDefault();
      onAccept?.();
      return;
    }

    if (event.key.toLowerCase() === 'r') {
      event.preventDefault();
      onReject?.();
      return;
    }

    if (event.key.toLowerCase() === 'd') {
      event.preventDefault();
      onDefer?.();
    }
  }

  function selectDelta(delta: number, sourceState: 'STEP' | 'TRACKING' = 'STEP'): void {
    const next = clampIndex(activeIndex + delta, items.length);
    if (next !== activeIndex) {
      interactionState = sourceState;
      momentumActiveIndex = null;
      onSelect?.(next);
      scheduleTransitionToIdle();
    }
  }

  function handleWheel(event: WheelEvent): void {
    cancelMotionOnNewInput();

    if (items.length === 0) {
      return;
    }

    const preventScroll = hasPointerFocus && shouldPreventWheelScroll(activeIndex, items.length, event.deltaY);
    if (preventScroll) {
      event.preventDefault();
    }

    const dtMs = lastWheelTs === 0 ? 16 : Math.max(1, event.timeStamp - lastWheelTs);
    const velocityPxPerMs = event.deltaY / dtMs;
    lastWheelTs = event.timeStamp;

    const result = computeWheelStep(event.deltaY, event.deltaMode, wheelAccumulator);
    wheelAccumulator = result.accumulator;

    if (result.step !== 0) {
      selectDelta(result.step, 'TRACKING');
      if (event.deltaMode === 0) {
        startMomentum(velocityPxPerMs);
      }
    } else {
      interactionState = 'TRACKING';
    }
  }

  function handleTouchStart(event: TouchEvent): void {
    cancelMotionOnNewInput();

    const touch = event.touches[0];
    if (!touch) return;
    hasPointerFocus = true;
    interactionState = 'TRACKING';
    momentumActiveIndex = null;
    touchState = startTouch(touch.clientX, touch.clientY, event.timeStamp);
  }

  function handleTouchMove(event: TouchEvent): void {
    cancelMotionOnNewInput();

    if (!touchState) return;
    const touch = event.touches[0];
    if (!touch) return;

    touchState = updateTouch(touchState, touch.clientX, touch.clientY, event.timeStamp);
    if (touchState.trackingSwipe) {
      event.preventDefault();
    }
  }

  function handleTouchEnd(): void {
    if (!touchState) {
      hasPointerFocus = false;
      return;
    }

    const release = resolveTouchRelease(touchState);
    const step = release.step;
    if (step !== 0) {
      selectDelta(step, 'TRACKING');
    }

    if (step !== 0 && shouldStartMomentum(release.momentumVelocityPxPerMs, TOUCH_FLING_PX_PER_MS)) {
      startMomentum(release.momentumVelocityPxPerMs);
    } else if (step === 0) {
      interactionState = 'IDLE';
    }

    touchState = null;
    hasPointerFocus = false;
  }

  function handleSlotClick(index: number): void {
    cancelMotionOnNewInput();
    const next = clampIndex(index, items.length);
    if (next !== activeIndex) {
      interactionState = 'STEP';
      momentumActiveIndex = null;
      onSelect?.(next);
      scheduleTransitionToIdle();
    }
  }

  onDestroy(() => {
    cancelMotion();
    for (const img of preloadedImages) {
      img.src = '';
    }
    preloadedImages = [];
  });

  $effect(() => {
    if (!shouldRunIdlePreload(interactionState)) {
      return;
    }
    if (typeof Image === 'undefined') {
      return;
    }
    if (items.length === 0) {
      return;
    }

    for (const img of preloadedImages) {
      img.src = '';
    }
    preloadedImages = [];

    const indexes = getPreloadIndexes(activeIndex, items.length, PRELOAD_RADIUS);
    preloadedImages = indexes.map((index) => {
      const img = new Image();
      img.decoding = 'async';
      img.src = `/api/v1/thumbnails/${items[index]?.sha256 ?? ''}`;
      return img;
    });

    return () => {
      for (const img of preloadedImages) {
        img.src = '';
      }
      preloadedImages = [];
    };
  });

  function slotStyle(index: number): string {
    const dist = Math.abs(index - activeIndex);
    if (dist === 0) {
      return [
        'transform: translateZ(60px)',
        'opacity: 1',
        `filter: blur(var(--wheel-blur-center))`,
        'z-index: 10',
      ].join('; ') + ';';
    } else if (dist === 1) {
      return [
        'transform: translateZ(-20px) scale(0.78)',
        'opacity: 0.7',
        `filter: blur(var(--wheel-blur-near))`,
        'z-index: 5',
      ].join('; ') + ';';
    } else {
      return [
        'transform: translateZ(-80px) scale(0.60)',
        'opacity: 0.4',
        `filter: blur(var(--wheel-blur-far))`,
        'z-index: 2',
      ].join('; ') + ';';
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<section
  class="wheel"
  data-testid="photo-wheel"
  data-interaction-state={interactionState}
  role="group"
  aria-label="Photo wheel"
  onwheel={handleWheel}
  onmouseenter={() => {
    hasPointerFocus = true;
  }}
  onmouseleave={() => {
    hasPointerFocus = false;
    wheelAccumulator = 0;
  }}
  ontouchstart={handleTouchStart}
  ontouchmove={handleTouchMove}
  ontouchend={handleTouchEnd}
  ontouchcancel={handleTouchEnd}
>
  {#if items.length === 0}
    <EmptyState message="No pending items in staging queue." />
  {:else}
    {@const window = getRenderWindow(activeIndex, items.length, RENDER_RADIUS)}
    {@const slotCounts = getWindowSlotCounts(window, items.length)}
    <div class="track">
      {#if slotCounts.left > 0}
        <div
          class="spacer"
          aria-hidden="true"
          style={`--slot-count: ${slotCounts.left}`}
        ></div>
      {/if}

      {#each items.slice(window.start, window.end + 1) as item, localIndex (item.sha256)}
        {@const index = window.start + localIndex}
        <div
          class="slot"
          class:is-active={index === activeIndex}
          style={slotStyle(index)}
          role="button"
          tabindex="0"
          onclick={() => handleSlotClick(index)}
          onkeydown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              handleSlotClick(index);
            }
          }}
        >
          <PhotoCard item={item} active={index === activeIndex} />
        </div>
      {/each}

      {#if slotCounts.right > 0}
        <div
          class="spacer"
          aria-hidden="true"
          style={`--slot-count: ${slotCounts.right}`}
        ></div>
      {/if}
    </div>
  {/if}
</section>

<style>
  .wheel {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    background: var(--surface-card);
    overflow-x: auto;
    perspective: 600px;
  }

  .track {
    display: flex;
    gap: var(--space-4);
    align-items: center;
    justify-content: center;
    padding-block: var(--space-8);
  }

  .slot {
    flex-shrink: 0;
    cursor: pointer;
    transition:
      transform var(--duration-slow) var(--easing-default),
      opacity var(--duration-slow) var(--easing-default),
      filter var(--duration-slow) var(--easing-default);
  }

  .spacer {
    flex: 0 0 calc(var(--slot-count) * (220px + var(--space-4)));
  }

  .slot.is-active {
    outline: 1px solid var(--action-primary);
    border-radius: var(--radius-md);
  }
</style>
