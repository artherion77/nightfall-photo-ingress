<script lang="ts">
  type ItemDetails = {
    filename: string;
    sha256: string;
    size_bytes?: number;
    account?: string;
    onedrive_id?: string;
  };

  interface Props {
    open?: boolean;
    item: ItemDetails | null;
    onClose?: () => void;
  }

  let { open = false, item, onClose }: Props = $props();

  function formatSize(bytes: number | undefined): string {
    if (bytes === undefined || Number.isNaN(bytes)) return 'n/a';
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

  function handleBackdropClick(): void {
    onClose?.();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose?.();
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div
    class="detail-sheet-backdrop"
    data-testid="detail-sheet-backdrop"
    role="presentation"
    onpointerdown={handleBackdropClick}
  >
    <div
      class="detail-sheet"
      data-testid="detail-sheet"
      role="dialog"
      aria-modal="true"
      aria-label="Item details"
      tabindex="-1"
      onpointerdown={(event) => event.stopPropagation()}
    >
      <header class="detail-sheet-header">
        <h2>Item Details</h2>
        <button type="button" class="close-button" aria-label="Close details" onclick={() => onClose?.()}>Close</button>
      </header>

      {#if item}
        <dl>
          <dt>Filename</dt><dd>{item.filename}</dd>
          <dt>SHA-256</dt>
          <dd>
            <input class="sha-input" type="text" readonly value={item.sha256} aria-label="Full SHA-256" />
          </dd>
          <dt>Size</dt><dd>{formatSize(item.size_bytes)}</dd>
          <dt>Account</dt><dd>{item.account ?? 'n/a'}</dd>
          <dt>OneDrive ID</dt><dd>{item.onedrive_id ?? 'n/a'}</dd>
        </dl>
      {:else}
        <p>No item selected.</p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .detail-sheet-backdrop {
    position: fixed;
    inset: 0;
    background: color-mix(in srgb, var(--color-bg-900) 55%, transparent);
    z-index: var(--z-overlay);
    display: flex;
    justify-content: flex-end;
  }

  .detail-sheet {
    width: min(460px, 92vw);
    height: 100%;
    background: var(--surface-card);
    border-left: 1px solid var(--border-default);
    box-shadow: var(--shadow-lg);
    padding: var(--space-4);
    overflow: auto;
  }

  .detail-sheet-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--space-4);
  }

  h2 {
    margin: 0;
    font-size: var(--text-xl);
  }

  .close-button {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--text-primary);
    padding: var(--space-1) var(--space-2);
    cursor: pointer;
  }

  .close-button:hover {
    border-color: var(--action-primary);
  }

  dl {
    margin: 0;
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: var(--space-2) var(--space-3);
    font-size: var(--text-sm);
  }

  dt {
    color: var(--text-muted);
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .sha-input {
    width: 100%;
    background: var(--surface-base);
    color: var(--text-primary);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    padding: var(--space-1) var(--space-2);
    font-size: var(--text-sm);
    font-family: var(--font-family-mono, monospace);
  }
</style>
