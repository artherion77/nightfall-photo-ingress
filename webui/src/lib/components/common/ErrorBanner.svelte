<script lang="ts">
  interface Props {
    message: string;
    onRetry?: () => void;
  }

  let { message, onRetry }: Props = $props();
</script>

<div class="error-banner">
  <div class="error-icon">⚠</div>
  <div class="error-text">
    <p class="error-message">{message}</p>
  </div>
  {#if onRetry}
    <button class="retry-button" onclick={onRetry}>Retry</button>
  {/if}
</div>

<style>
  .error-banner {
    background-color: var(--action-reject-surface);
    border: 1px solid var(--action-reject);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .error-icon {
    font-size: var(--text-xl);
    color: var(--action-reject);
    flex-shrink: 0;
  }

  .error-text {
    flex: 1;
  }

  .error-message {
    margin: 0;
    font-size: var(--text-base);
    color: var(--text-primary);
  }

  .retry-button {
    padding: var(--space-2) var(--space-3);
    background-color: var(--action-reject);
    color: white;
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
    font-size: var(--text-base);
    font-weight: var(--text-md-weight);
    transition: all var(--duration-default) var(--easing-default);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .retry-button:hover {
    background-color: #f67575;
  }
</style>
