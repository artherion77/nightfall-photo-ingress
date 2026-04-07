<script lang="ts">
  import {
    fallbackLabel,
    imageErrorState,
    imageLoadedState,
    shouldShowFallback,
    shouldShowImage,
    shouldShowSkeleton,
    thumbnailSrc,
    type ImageState,
  } from './photocard-image';

  interface Props {
    item: {
      sha256: string;
      filename: string;
      account?: string;
      first_seen_at?: string;
    };
    active?: boolean;
  }

  let { item, active = false }: Props = $props();
  let imageState: ImageState = $state('loading');

  $effect(() => {
    item.sha256;
    imageState = 'loading';
  });

  function formatTimestamp(ts: string | undefined): string {
    if (!ts) return '';
    const d = new Date(ts);
    const hh = d.getHours().toString().padStart(2, '0');
    const mm = d.getMinutes().toString().padStart(2, '0');
    return `Captured at ${hh}:${mm}`;
  }

  function handleImageLoad(): void {
    imageState = imageLoadedState();
  }

  function handleImageError(): void {
    imageState = imageErrorState();
  }
</script>

<article class="photo-card" class:active data-testid="photo-card">
  <div class="thumb" data-testid="photo-thumb" data-state={imageState}>
    <img
      class="thumb-image"
      class:is-hidden={!shouldShowImage(imageState)}
      src={thumbnailSrc(item.sha256)}
      alt={item.filename}
      loading="lazy"
      decoding="async"
      onload={handleImageLoad}
      onerror={handleImageError}
    />

    {#if shouldShowSkeleton(imageState)}
      <div class="thumb-skeleton" data-testid="thumb-skeleton" aria-hidden="true"></div>
    {/if}

    {#if shouldShowFallback(imageState)}
      <div class="thumb-fallback" data-testid="thumb-fallback" role="img" aria-label={fallbackLabel(item.filename)}>
        {fallbackLabel(item.filename)}
      </div>
    {/if}
  </div>
  <h3>{item.filename}</h3>
  <p>SHA-256: {item.sha256.slice(0, 16)}...</p>
  <p>{item.account ?? 'unknown account'}</p>
  <p>{formatTimestamp(item.first_seen_at)}</p>
</article>

<style>
  .photo-card {
    min-width: 220px;
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
    opacity: 0.7;
  }

  .photo-card.active {
    opacity: 1;
    border-color: var(--action-primary);
  }

  .thumb {
    width: 100%;
    aspect-ratio: 4 / 3;
    min-height: 165px;
    border-radius: var(--radius-md);
    background: var(--surface-hover);
    position: relative;
    overflow: hidden;
    margin-bottom: var(--space-3);
  }

  .thumb-image {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .thumb-image.is-hidden {
    opacity: 0;
  }

  .thumb-skeleton,
  .thumb-fallback {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
  }

  .thumb-skeleton {
    background: linear-gradient(
      90deg,
      var(--surface-hover) 0%,
      var(--surface-raised) 50%,
      var(--surface-hover) 100%
    );
    background-size: 200% 100%;
    animation: skeletonPulse var(--duration-slow) var(--easing-default) infinite;
  }

  .thumb-fallback {
    color: var(--text-muted);
    font-size: var(--text-xs);
    letter-spacing: 0.04em;
    text-align: center;
    padding: var(--space-2);
    background: var(--surface-hover);
  }

  @keyframes skeletonPulse {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }

  h3 {
    margin: 0 0 var(--space-2) 0;
    font-size: var(--text-base);
  }

  p {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }
</style>
