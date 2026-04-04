<script lang="ts">
  import ActionButton from '$lib/components/common/ActionButton.svelte';

  interface Props {
    disabled?: boolean;
    onAccept?: () => void;
    onReject?: () => void;
  }

  let { disabled = false, onAccept, onReject }: Props = $props();
</script>

<section class="triage-controls" data-testid="triage-controls">
  <div class="inline-controls" data-testid="triage-inline-controls">
    <ActionButton variant="accept" label="Accept" {disabled} onclick={() => onAccept?.()} />
    <ActionButton variant="reject" label="Reject" {disabled} onclick={() => onReject?.()} />
  </div>

  <div class="cta-controls" data-testid="triage-cta-controls">
    <ActionButton variant="accept" label="Accept Selected" {disabled} onclick={() => onAccept?.()} />
    <ActionButton variant="reject" label="Reject Selected" {disabled} onclick={() => onReject?.()} />
  </div>

  <p class="hint">Keyboard: A = Accept, R = Reject, D = Defer, Arrow keys = navigate</p>
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
