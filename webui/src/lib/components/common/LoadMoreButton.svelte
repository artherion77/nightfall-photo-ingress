<script lang="ts">
  interface Props {
    loading?: boolean;
    hasMore: boolean;
    onLoadMore: () => void;
  }

  let { loading = false, hasMore, onLoadMore }: Props = $props();
</script>

<div class="load-more-container">
  {#if hasMore}
    <button class="load-more-button" disabled={loading} onclick={onLoadMore}>
      {#if loading}
        <span class="spinner"></span>
        Loading more...
      {:else}
        Load more
      {/if}
    </button>
  {/if}
</div>

<style>
  .load-more-container {
    display: flex;
    justify-content: center;
    padding: var(--space-5) 0;
  }

  .load-more-button {
    padding: var(--space-3) var(--space-5);
    background-color: var(--surface-hover);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: var(--text-base);
    font-weight: var(--text-md-weight);
    cursor: pointer;
    transition: all var(--duration-default) var(--easing-default);
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-family: var(--font-family-base);
  }

  .load-more-button:hover:not(:disabled) {
    background-color: var(--surface-raise);
    border-color: var(--border-strong);
  }

  .load-more-button:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid var(--color-border-subtle);
    border-top-color: var(--action-primary);
    border-radius: 50%;
    animation: spin var(--duration-default) linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
