<script lang="ts">
  import ActionButton from '$lib/components/common/ActionButton.svelte';
  import { generateIdempotencyKey } from '$lib/api/triage';

  type ControlMode = 'inline' | 'cta' | 'both';

  interface Props {
    disabled?: boolean;
    mode?: ControlMode;
    dragActive?: boolean;
    onAccept?: (idempotencyKey: string) => void;
    onReject?: (idempotencyKey: string) => void;
  }

  let { disabled = false, mode = 'both', dragActive = false, onAccept, onReject }: Props = $props();
  let dragOverTarget = $state<'accept' | 'reject' | null>(null);

  function acceptWithKey() {
    onAccept?.(generateIdempotencyKey());
  }

  function rejectWithKey() {
    onReject?.(generateIdempotencyKey());
  }

  function hasPhotoDragType(event: DragEvent): boolean {
    const types = event.dataTransfer?.types;
    if (!types) return false;
    return types.includes('application/x-nightfall-sha256') || types.includes('text/plain');
  }

  function extractedSha(event: DragEvent): string {
    const transfer = event.dataTransfer;
    if (!transfer) return '';
    return transfer.getData('application/x-nightfall-sha256') || transfer.getData('text/plain') || '';
  }

  function handleDragOver(event: DragEvent, target: 'accept' | 'reject'): void {
    if (!dragActive || disabled) {
      return;
    }

    if (!hasPhotoDragType(event)) {
      return;
    }

    event.preventDefault();
    dragOverTarget = target;
  }

  function handleDragLeave(target: 'accept' | 'reject'): void {
    if (dragOverTarget === target) {
      dragOverTarget = null;
    }
  }

  function handleDrop(event: DragEvent, target: 'accept' | 'reject'): void {
    if (!dragActive || disabled) {
      return;
    }

    event.preventDefault();
    const sha = extractedSha(event);
    dragOverTarget = null;
    if (!sha) {
      return;
    }

    if (target === 'accept') {
      acceptWithKey();
      return;
    }
    rejectWithKey();
  }
</script>

<section
  class="triage-controls"
  class:inline-only={mode === 'inline'}
  class:cta-only={mode === 'cta'}
  data-testid="triage-controls"
>
  {#if mode === 'inline' || mode === 'both'}
    <div class="inline-controls" data-testid="triage-inline-controls">
      <ActionButton variant="accept" label="Accept" {disabled} onclick={acceptWithKey} />
      <ActionButton variant="reject" label="Reject" {disabled} onclick={rejectWithKey} />
    </div>
  {/if}

  {#if mode === 'cta' || mode === 'both'}
    <div class="cta-controls" data-testid="triage-cta-controls">
      <button
        type="button"
        class="cta-button cta-accept"
        class:is-drag-over={dragOverTarget === 'accept'}
        data-testid="triage-cta-accept"
        aria-label="Accept"
        {disabled}
        onclick={acceptWithKey}
        ondragover={(event) => handleDragOver(event, 'accept')}
        ondragleave={() => handleDragLeave('accept')}
        ondrop={(event) => handleDrop(event, 'accept')}
      >
        <span class="cta-icon" aria-hidden="true">&#9995;&#65038;</span>
        <span class="cta-copy">
          <span class="cta-label">Accept</span>
          <span class="cta-sub">Drag &amp; Drop photos here</span>
        </span>
      </button>
      <button
        type="button"
        class="cta-button cta-reject"
        class:is-drag-over={dragOverTarget === 'reject'}
        data-testid="triage-cta-reject"
        aria-label="Reject"
        {disabled}
        onclick={rejectWithKey}
        ondragover={(event) => handleDragOver(event, 'reject')}
        ondragleave={() => handleDragLeave('reject')}
        ondrop={(event) => handleDrop(event, 'reject')}
      >
        <span class="cta-icon" aria-hidden="true">&#9995;&#65038;</span>
        <span class="cta-copy">
          <span class="cta-label">Reject</span>
          <span class="cta-sub">Drag &amp; Drop photos here</span>
        </span>
      </button>
    </div>
  {/if}

  {#if mode !== 'inline'}
    <p class="hint">Keyboard: A = Accept, R = Reject, D = Defer, Arrow keys = navigate</p>
  {/if}
</section>

<style>
  .triage-controls {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  .triage-controls.inline-only,
  .triage-controls.cta-only {
    padding: 0;
    border: 0;
    background: transparent;
  }

  .inline-controls {
    display: flex;
    gap: var(--space-2);
    justify-content: center;
  }

  .cta-controls {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }

  .cta-button {
    min-height: clamp(84px, 10vh, 96px);
    border-radius: var(--radius-md);
    border: 2px solid transparent;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
    transition:
      box-shadow var(--duration-default) var(--easing-default),
      border-color var(--duration-default) var(--easing-default),
      transform var(--duration-default) var(--easing-default),
      background-color var(--duration-default) var(--easing-default);
  }

  .cta-copy {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    min-width: 0;
  }

  .cta-label {
    font-size: var(--text-xl);
    font-weight: var(--text-md-weight);
    line-height: 1.15;
  }

  .cta-sub {
    font-size: var(--text-sm);
    line-height: 1.2;
    opacity: 0.85;
    white-space: nowrap;
    text-overflow: ellipsis;
    overflow: hidden;
  }

  .cta-icon {
    font-size: var(--text-xl);
    line-height: 1;
    display: inline-block;
    color: inherit;
    flex: 0 0 auto;
  }

  .cta-accept {
    border-color: var(--border-accept);
    background-color: color-mix(in srgb, var(--action-accept) 15%, var(--color-bg-900) 85%);
    color: var(--border-accept);
  }

  .cta-accept:hover:not(:disabled) {
    box-shadow: var(--shadow-accept-glow);
    background-color: color-mix(in srgb, var(--action-accept) 20%, var(--color-bg-900) 80%);
  }

  .cta-accept:active:not(:disabled) {
    box-shadow: var(--shadow-accept-glow);
    transform: translateY(1px);
    background-color: color-mix(in srgb, var(--action-accept) 25%, var(--color-bg-900) 75%);
  }

  .cta-accept.is-drag-over:not(:disabled) {
    box-shadow: var(--shadow-accept-glow);
    background-color: color-mix(in srgb, var(--action-accept) 20%, var(--color-bg-900) 80%);
  }

  .cta-reject {
    border-color: var(--border-reject);
    background-color: color-mix(in srgb, var(--action-reject) 15%, var(--color-bg-900) 85%);
    color: var(--border-reject);
  }

  .cta-reject:hover:not(:disabled) {
    box-shadow: var(--shadow-reject-glow);
    background-color: color-mix(in srgb, var(--action-reject) 20%, var(--color-bg-900) 80%);
  }

  .cta-reject:active:not(:disabled) {
    box-shadow: var(--shadow-reject-glow);
    transform: translateY(1px);
    background-color: color-mix(in srgb, var(--action-reject) 20%, var(--color-bg-900) 80%);
  }

  .cta-reject.is-drag-over:not(:disabled) {
    box-shadow: var(--shadow-reject-glow);
    background-color: color-mix(in srgb, var(--action-reject) 20%, var(--color-bg-900) 80%);
  }

  .cta-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .hint {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  @media (max-width: 720px) {
    .cta-controls {
      grid-template-columns: 1fr;
    }
  }
</style>
