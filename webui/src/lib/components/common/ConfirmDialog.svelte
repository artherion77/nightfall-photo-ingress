<script lang="ts">
  interface Props {
    open?: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
    onCancel: () => void;
  }

  let { open = false, title, message, onConfirm, onCancel }: Props = $props();
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="dialog-overlay" onclick={onCancel}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="dialog-content" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h2 class="dialog-title">{title}</h2>
      <p class="dialog-message">{message}</p>
      <div class="dialog-actions">
        <button class="btn-cancel" onclick={onCancel}>Cancel</button>
        <button class="btn-confirm" onclick={onConfirm}>Confirm</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .dialog-overlay {
    position: fixed;
    inset: 0;
    background-color: var(--surface-overlay);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: var(--z-overlay);
  }

  .dialog-content {
    background-color: var(--surface-card);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-lg);
    padding: var(--space-6);
    max-width: 400px;
    box-shadow: var(--shadow-lg);
    z-index: var(--z-modal);
  }

  .dialog-title {
    margin: 0 0 var(--space-3) 0;
    font-size: var(--text-lg);
    font-weight: var(--text-lg-weight);
    color: var(--text-primary);
  }

  .dialog-message {
    margin: 0 0 var(--space-5) 0;
    font-size: var(--text-base);
    color: var(--text-secondary);
    line-height: var(--text-base-line-height);
  }

  .dialog-actions {
    display: flex;
    gap: var(--space-3);
    justify-content: flex-end;
  }

  button {
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-md);
    border: none;
    font-size: var(--text-base);
    font-weight: var(--text-md-weight);
    cursor: pointer;
    transition: all var(--duration-default) var(--easing-default);
    font-family: var(--font-family-base);
  }

  .btn-cancel {
    background-color: var(--surface-hover);
    color: var(--text-primary);
  }

  .btn-cancel:hover {
    background-color: var(--color-bg-600);
  }

  .btn-confirm {
    background-color: var(--action-primary);
    color: var(--color-bg-900);
  }

  .btn-confirm:hover {
    background-color: var(--action-primary-hover);
  }
</style>
