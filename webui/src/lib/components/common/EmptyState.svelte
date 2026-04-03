<script lang="ts">
  interface Props {
    message: string;
    actionLabel?: string;
    onAction?: () => void;
  }

  let { message, actionLabel, onAction }: Props = $props();
</script>

<div class="empty-state">
  <div class="empty-icon">∅</div>
  <p class="empty-message">{message}</p>
  {#if actionLabel && onAction}
    <button class="empty-action" onclick={onAction}>
      {actionLabel}
    </button>
  {/if}
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--space-8);
    text-align: center;
  }

  .empty-icon {
    font-size: 48px;
    color: var(--text-muted);
    margin-bottom: var(--space-4);
  }

  .empty-message {
    margin: 0 0 var(--space-5) 0;
    font-size: var(--text-base);
    color: var(--text-muted);
    line-height: var(--text-base-line-height);
    max-width: 300px;
  }

  .empty-action {
    padding: var(--space-2) var(--space-4);
    background-color: var(--action-primary);
    color: var(--color-bg-900);
    border: none;
    border-radius: var(--radius-md);
    font-size: var(--text-base);
    font-weight: var(--text-md-weight);
    cursor: pointer;
    transition: all var(--duration-default) var(--easing-default);
    font-family: var(--font-family-base);
  }

  .empty-action:hover {
    background-color: var(--action-primary-hover);
  }
</style>
