<script lang="ts">
  import { onDestroy } from 'svelte';
  import EmptyState from '$lib/components/common/EmptyState.svelte';
  import PhotoCard from './PhotoCard.svelte';
  import { thumbnailSrc } from './photocard-image';
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
    PRELOAD_RADIUS,
    RENDER_RADIUS,
    shouldRunIdlePreload,
  } from './photowheel-windowing';

  interface Item {
    sha256: string;
    filename: string;
    account?: string;
    first_seen_at?: string;
    size_bytes?: number;
    onedrive_id?: string;
  }

  interface Props {
    items: Item[];
    activeIndex?: number;
    onSelect?: (index: number) => void;
    onAccept?: () => void;
    onReject?: () => void;
    onDefer?: () => void;
    onDragStateChange?: (dragging: boolean) => void;
    onOpenDetails?: () => void;
    actionsDisabled?: boolean;
  }

  let { items, activeIndex = 0, onSelect, onAccept, onReject, onDefer, onDragStateChange, onOpenDetails, actionsDisabled = false }: Props = $props();
  const SLOT_COUNT = 2 * RENDER_RADIUS + 1;

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
  let dragging = $state(false);

  const TRANSITION_SETTLE_MS = 220;

    // Phase 2: directional content-entrance animation.
    // When activeIndex changes, the center slot receives a transient translateX
    // offset in the direction the new content enters from.  The CSS transition
    // (350ms) then animates it back to the stable Phase 1 centre position.
      let prevActiveIndexForAnim: number | null = null;

      // centerSlotEl is bound to the center-slot div via bind:this so that the
      // Web Animations API can drive the entrance animation directly on the element
      // without going through Svelte's CSS-transition path (which requires the
      // browser to see two distinct paint states — not guaranteed when both the
      // +offsetX and the 0px assignments happen inside the same task).
        let centerSlotEl: HTMLDivElement | null = $state(null);

      $effect(() => {
        const curr = activeIndex;
        if (prevActiveIndexForAnim !== null && curr !== prevActiveIndexForAnim && centerSlotEl) {
          const dir: 1 | -1 = curr > prevActiveIndexForAnim ? 1 : -1;
          const offsetX = dir * 60;
          // dir > 0 → navigate right → new content enters from the right (+X).
          // dir < 0 → navigate left  → new content enters from the left  (−X).
          centerSlotEl.animate(
            [
              {
                transform: `translateX(-50%) translateY(-50%) translateX(${offsetX}px) translateZ(60px) rotateY(0deg) scale(1.0)`,
              },
              {
                transform:
                  'translateX(-50%) translateY(-50%) translateX(0px) translateZ(60px) rotateY(0deg) scale(1.0)',
              },
            ],
              { duration: 200, easing: 'cubic-bezier(0.2, 0, 0, 1)', fill: 'none' },
          );
        }
        prevActiveIndexForAnim = curr;
      });
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
    if (dragging) {
      event.preventDefault();
      return;
    }

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
    if (dragging) {
      event.preventDefault();
      return;
    }

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
    if (dragging) {
      return;
    }

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
    if (dragging) {
      return;
    }

    cancelMotionOnNewInput();
    const next = clampIndex(index, items.length);
    if (next !== activeIndex) {
      interactionState = 'STEP';
      momentumActiveIndex = null;
      onSelect?.(next);
      scheduleTransitionToIdle();
    }
  }

  function handleDragStart(event: DragEvent, itemIndex: number): void {
    const item = items[itemIndex];
    if (!item) {
      event.preventDefault();
      return;
    }

    cancelMotion();
    interactionState = 'IDLE';
    const transfer = event.dataTransfer;
    if (!transfer) {
      event.preventDefault();
      return;
    }

    transfer.effectAllowed = 'move';
    transfer.setData('text/plain', item.sha256);
    transfer.setData('application/x-nightfall-sha256', item.sha256);
    dragging = true;
    onDragStateChange?.(true);
  }

  function handleDragEnd(): void {
    dragging = false;
    onDragStateChange?.(false);
  }

  onDestroy(() => {
    if (dragging) {
      onDragStateChange?.(false);
    }
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
      img.src = thumbnailSrc(items[index]?.sha256 ?? '');
      return img;
    });

    return () => {
      for (const img of preloadedImages) {
        img.src = '';
      }
      preloadedImages = [];
    };
  });

  function slotStyle(slotPos: number): string {
    const delta = slotPos - RENDER_RADIUS;
    const dist = Math.abs(delta);
    const direction = delta < 0 ? 1 : delta > 0 ? -1 : 0;
    const left = delta === 0 ? '50%' : `calc(50% + (${delta} * var(--slot-offset)))`;
    const rotationDeg = dist === 0 ? 0 : dist === 1 ? 15 : 30;
    const overlapTranslatePx = dist === 0 ? 0 : dist === 1 ? 48 : 64;
    if (dist === 0) {
      return [
        `left: ${left}`,
          'transform: translateX(-50%) translateY(-50%) translateZ(60px) rotateY(0deg) scale(1.0)',
        'opacity: 1',
        `filter: blur(var(--wheel-blur-center))`,
        'z-index: 10',
      ].join('; ') + ';';
    } else if (dist === 1) {
      return [
        `left: ${left}`,
        `transform: translateX(-50%) translateY(-50%) translateX(${direction * overlapTranslatePx}px) translateZ(-20px) rotateY(${direction * rotationDeg}deg) scale(0.78)`,
        'opacity: 0.7',
        `filter: blur(var(--wheel-blur-near))`,
        'z-index: 5',
      ].join('; ') + ';';
    } else {
      return [
        `left: ${left}`,
        `transform: translateX(-50%) translateY(-50%) translateX(${direction * overlapTranslatePx}px) translateZ(-80px) rotateY(${direction * rotationDeg}deg) scale(0.60)`,
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
    <div class="stage">
      {#each Array.from({ length: SLOT_COUNT }, (_, i) => i) as slotPos (slotPos)}
        {@const itemIndex = activeIndex - RENDER_RADIUS + slotPos}
        {#if itemIndex >= 0 && itemIndex < items.length}
          {#if slotPos === RENDER_RADIUS}
            <div
              class="slot is-active"
              class:is-dragging={dragging}
              style={slotStyle(slotPos)}
                bind:this={centerSlotEl}
              role="button"
              tabindex={0}
              draggable="true"
              onclick={() => handleSlotClick(itemIndex)}
              ondragstart={(event) => handleDragStart(event, itemIndex)}
              ondragend={handleDragEnd}
              onkeydown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  handleSlotClick(itemIndex);
                }
              }}
            >
              <PhotoCard item={items[itemIndex]} active={true} onOpenDetails={onOpenDetails} onAccept={onAccept} onReject={onReject} actionsDisabled={actionsDisabled} />
            </div>
          {:else}
            <div class="slot" style={slotStyle(slotPos)} aria-hidden="true">
              <PhotoCard item={items[itemIndex]} active={false} />
            </div>
          {/if}
        {/if}
      {/each}
    </div>
  {/if}
</section>

<style>
  .wheel {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    background: var(--surface-card);
    overflow-x: hidden;
    overflow-y: hidden;
    perspective: 860px;
    overscroll-behavior: contain;
    height: 100%;
    box-sizing: border-box;
  }

  .stage {
    position: relative;
    width: 100%;
    overflow: visible;
    --slot-width: clamp(280px, 38vw, min(480px, 50vw));
    --slot-gap: var(--space-2);
    --slot-offset: calc(var(--slot-width) * 0.86 + var(--slot-gap));
    height: 100%;
    box-sizing: border-box;
    padding-block: var(--space-5);
  }

  .slot {
    position: absolute;
    top: 50%;
    width: var(--slot-width);
    transform-origin: center center;
    cursor: pointer;
    transition:
      transform var(--duration-slow) var(--easing-default),
      opacity var(--duration-slow) var(--easing-default),
      filter var(--duration-slow) var(--easing-default);
  }

  .slot.is-active {
    border-radius: var(--radius-md);
  }

  .slot.is-active.is-dragging {
    opacity: 0.5 !important;
  }
</style>
