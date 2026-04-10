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
      size_bytes?: number;
      onedrive_id?: string;
    };
    active?: boolean;
    onOpenDetails?: () => void;
    onAccept?: () => void;
    onReject?: () => void;
    actionsDisabled?: boolean;
  }

  let { item, active = false, onOpenDetails, onAccept, onReject, actionsDisabled = false }: Props = $props();
  let imageState: ImageState = $state('loading');
  let showSidecar = $state(false);
  let previousSha256: string | undefined = $state(undefined);
  let currentEpoch = $state(0);

  const THUMBNAIL_SHA_RE = /\/api\/v1\/thumbnails\/([^/?#]+)/;

  function currentSha256(): string | undefined {
    return item.sha256 || undefined;
  }

  function isDefinedSha(sha: string | undefined): sha is string {
    return typeof sha === 'string' && sha.length > 0;
  }

  function parseEventSha256(event: Event): string | undefined {
    const target = event.currentTarget;
    if (!(target instanceof HTMLImageElement)) return undefined;
    const source = target.currentSrc || target.src;
    const match = THUMBNAIL_SHA_RE.exec(source);
    return match?.[1];
  }

  function parseEventEpoch(event: Event): number | undefined {
    const target = event.currentTarget;
    if (!(target instanceof HTMLImageElement)) return undefined;
    const rawEpoch = target.dataset.imageEpoch;
    if (!rawEpoch) return undefined;
    const parsed = Number(rawEpoch);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  function shouldAcceptImageEvent(event: Event): boolean {
    const eventEpoch = parseEventEpoch(event);
    const eventSha256 = parseEventSha256(event);
    const activeSha256 = currentSha256();
    return eventEpoch === currentEpoch && eventSha256 === activeSha256;
  }

  $effect(() => {
    const nextSha256 = currentSha256();
    if (!isDefinedSha(nextSha256)) return;
    if (nextSha256 === previousSha256) return;
    currentEpoch += 1;
    previousSha256 = nextSha256;
    imageState = 'loading';
  });

  function formatTimestamp(ts: string | undefined): string {
    if (!ts) return '';
    const d = new Date(ts);
    const hh = d.getHours().toString().padStart(2, '0');
    const mm = d.getMinutes().toString().padStart(2, '0');
    return `Captured at ${hh}:${mm}`;
  }

  function formatSize(bytes: number | undefined): string {
    if (bytes === undefined || Number.isNaN(bytes)) return '';
    if (bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let value = bytes / 1024;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }
    return `${value.toFixed(1)} ${units[unitIndex]}`;
  }

  function handleImageLoad(event: Event): void {
    if (!shouldAcceptImageEvent(event)) return;
    imageState = imageLoadedState();
  }

  function handleImageError(event: Event): void {
    if (!shouldAcceptImageEvent(event)) return;
    imageState = imageErrorState();
  }

  function sidecarEntries(): Array<{ label: string; value: string }> {
    const entries: Array<{ label: string; value: string }> = [];
    entries.push({ label: 'Account', value: item.account ?? 'n/a' });
    if (item.first_seen_at) {
      entries.push({ label: 'Captured', value: formatTimestamp(item.first_seen_at) });
    }
    if (item.size_bytes !== undefined) {
      entries.push({ label: 'Size', value: formatSize(item.size_bytes) });
    }
    entries.push({ label: 'SHA-256', value: item.sha256 });
    if (item.onedrive_id) {
      entries.push({ label: 'OneDrive ID', value: item.onedrive_id });
    }
    return entries;
  }
</script>

<article class="photo-card" class:active data-testid="photo-card" data-sha256={item.sha256}>
  <div class="thumb" data-testid="photo-thumb" data-state={imageState}>
    <img
      class="thumb-image"
      class:is-hidden={!shouldShowImage(imageState)}
      src={thumbnailSrc(item.sha256)}
      data-image-epoch={currentEpoch}
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
  <div class="card-footer">
    <p class="compact-meta" data-testid="photo-card-compact-meta">{item.account ?? 'unknown account'} | {item.filename}</p>
    {#if active}
      <div class="details-anchor" role="presentation">
        <button
          type="button"
          class={`details-trigger${showSidecar ? ' is-sidecar-open' : ''}`}
          data-testid="photo-card-details-trigger"
          aria-label="Open item details"
          onmouseenter={() => {
            showSidecar = true;
          }}
          onmouseleave={() => {
            showSidecar = false;
          }}
          onfocus={() => {
            showSidecar = true;
          }}
          onblur={() => {
            showSidecar = false;
          }}
          onclick={(event) => {
            event.stopPropagation();
            onOpenDetails?.();
          }}
        >
          <span class="details-glyph" aria-hidden="true">i</span>
        </button>
        {#if showSidecar}
          <section class="sidecar-popover" data-testid="photo-card-sidecar-popover" aria-label="Photo sidecar information">
            <h4>Sidecar Information</h4>
            <dl>
              {#each sidecarEntries() as entry}
                <dt>{entry.label}</dt>
                <dd>{entry.value}</dd>
              {/each}
            </dl>
          </section>
        {/if}
      </div>
    {/if}
  </div>
  {#if active}
    <div class="card-actions" data-testid="photo-card-actions">
      <button
        type="button"
        class="card-action-btn card-action-accept"
        data-testid="photo-card-action-accept"
        aria-label="Accept"
        disabled={actionsDisabled}
        onclick={onAccept}
      >
        Accept
      </button>
      <button
        type="button"
        class="card-action-btn card-action-reject"
        data-testid="photo-card-action-reject"
        aria-label="Reject"
        disabled={actionsDisabled}
        onclick={onReject}
      >
        Reject
      </button>
    </div>
  {/if}
  <h3 class="visually-hidden">{item.filename}</h3>
  <p class="visually-hidden">SHA-256: {item.sha256.slice(0, 16)}...</p>
</article>

<style>
  .photo-card {
    position: relative;
    width: 100%;
    min-width: 0;
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

  .card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }

  .details-anchor {
    position: relative;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    flex-shrink: 0;
  }

  .details-trigger {
    width: 28px;
    height: 28px;
    padding: 0;
    border-radius: var(--radius-full);
    border: 2px solid var(--border-default);
    background: color-mix(in srgb, var(--surface-card) 88%, transparent);
    color: var(--text-primary);
    cursor: pointer;
    display: grid;
    place-items: center;
    z-index: var(--z-raised);
    transition:
      border-color var(--duration-default) var(--easing-default),
      background-color var(--duration-default) var(--easing-default);
    box-sizing: border-box;
    position: relative;
  }

  .details-glyph {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    font-size: 14px;
    line-height: 1;
    font-weight: 600;
    pointer-events: none;
  }

  .details-trigger:hover {
    border-color: var(--action-primary);
    background: color-mix(in srgb, var(--surface-card) 95%, transparent);
  }

  .details-trigger.is-sidecar-open {
    border-color: var(--action-primary);
    background: color-mix(in srgb, var(--surface-card) 95%, transparent);
  }

  .thumb {
    width: 100%;
    aspect-ratio: 4 / 3;
    min-height: 165px;
    border-radius: var(--radius-md);
    background: var(--surface-hover);
    position: relative;
    overflow: hidden;
    margin-bottom: 0;
  }

  .sidecar-popover {
    position: absolute;
    right: 0;
    bottom: calc(100% + var(--space-2));
    width: min(340px, calc(100vw - 96px));
    padding: var(--space-3);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
    box-shadow: var(--shadow-md);
    z-index: var(--z-dropdown);
  }

  .sidecar-popover h4 {
    margin: 0 0 var(--space-2) 0;
    font-size: var(--text-sm);
    color: var(--text-primary);
  }

  .sidecar-popover dl {
    margin: 0;
    display: grid;
    grid-template-columns: 100px 1fr;
    gap: var(--space-1) var(--space-2);
    font-size: var(--text-sm);
  }

  .sidecar-popover dt {
    color: var(--text-muted);
  }

  .sidecar-popover dd {
    margin: 0;
    color: var(--text-primary);
    overflow-wrap: anywhere;
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

  .compact-meta {
    margin: 0;
    font-size: var(--text-base);
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
    min-width: 0;
  }

  .card-actions {
    position: absolute;
    left: 100%;
    bottom: 10%;
    flex-direction: column;
    display: flex;
    gap: var(--space-2);
    margin-left: var(--space-3);
    z-index: var(--z-raised);
  }

  .card-action-btn {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md);
    border: none;
    font-size: var(--text-base);
    font-weight: var(--text-md-weight);
    cursor: pointer;
    transition: all var(--duration-default) var(--easing-default);
  }

  .card-action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .card-action-accept {
    background-color: var(--action-accept);
    color: white;
  }

  .card-action-accept:hover:not(:disabled) {
    background-color: #10e8cc;
  }

  .card-action-reject {
    background-color: var(--action-reject);
    color: white;
  }

  .card-action-reject:hover:not(:disabled) {
    background-color: #f67575;
  }

  h3 {
    margin: 0;
    font-size: var(--text-base);
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }
</style>
