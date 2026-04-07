<script lang="ts">
  import EmptyState from '$lib/components/common/EmptyState.svelte';
  import PhotoCard from './PhotoCard.svelte';
  import {
    clampIndex,
    computeWheelStep,
    resolveTouchStep,
    shouldPreventWheelScroll,
    startTouch,
    updateTouch,
    type TouchState,
  } from './photowheel-input';

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
  let hasPointerFocus = false;
  let touchState: TouchState | null = null;

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      onSelect?.(Math.max(activeIndex - 1, 0));
      return;
    }

    if (event.key === 'ArrowRight') {
      event.preventDefault();
      onSelect?.(Math.min(activeIndex + 1, Math.max(items.length - 1, 0)));
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

  function selectDelta(delta: number): void {
    const next = clampIndex(activeIndex + delta, items.length);
    if (next !== activeIndex) {
      onSelect?.(next);
    }
  }

  function handleWheel(event: WheelEvent): void {
    if (items.length === 0) {
      return;
    }

    const preventScroll = hasPointerFocus && shouldPreventWheelScroll(activeIndex, items.length, event.deltaY);
    if (preventScroll) {
      event.preventDefault();
    }

    const result = computeWheelStep(event.deltaY, event.deltaMode, wheelAccumulator);
    wheelAccumulator = result.accumulator;

    if (result.step !== 0) {
      selectDelta(result.step);
    }
  }

  function handleTouchStart(event: TouchEvent): void {
    const touch = event.touches[0];
    if (!touch) return;
    hasPointerFocus = true;
    touchState = startTouch(touch.clientX, touch.clientY, event.timeStamp);
  }

  function handleTouchMove(event: TouchEvent): void {
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

    const step = resolveTouchStep(touchState);
    if (step !== 0) {
      selectDelta(step);
    }

    touchState = null;
    hasPointerFocus = false;
  }

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
    <div class="track">
      {#each items as item, index}
        <div
          class="slot"
          class:is-active={index === activeIndex}
          style={slotStyle(index)}
          role="button"
          tabindex="0"
          onclick={() => onSelect?.(index)}
          onkeydown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              onSelect?.(index);
            }
          }}
        >
          <PhotoCard item={item} active={index === activeIndex} />
        </div>
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

  .slot.is-active {
    outline: 1px solid var(--action-primary);
    border-radius: var(--radius-md);
  }
</style>
