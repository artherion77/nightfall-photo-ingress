<script lang="ts">
  import ActionButton from '$lib/components/common/ActionButton.svelte';
  import { generateIdempotencyKey } from '$lib/api/triage';

  type ControlMode = 'inline' | 'cta' | 'both';

  interface Props {
    disabled?: boolean;
    mode?: ControlMode;
    onAccept?: (idempotencyKey: string) => void;
    onReject?: (idempotencyKey: string) => void;
  }

  let { disabled = false, mode = 'both', onAccept, onReject }: Props = $props();

  function acceptWithKey() {
    onAccept?.(generateIdempotencyKey());
  }

  function rejectWithKey() {
    onReject?.(generateIdempotencyKey());
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
      <ActionButton variant="accept" label="Accept Selected" {disabled} onclick={acceptWithKey} />
      <ActionButton variant="reject" label="Reject Selected" {disabled} onclick={rejectWithKey} />
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
