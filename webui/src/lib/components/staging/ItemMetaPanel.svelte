<script lang="ts">
  interface Props {
    item: {
      filename: string;
      sha256: string;
      size_bytes: number;
      account?: string;
      onedrive_id?: string;
    } | null;
  }

  let { item }: Props = $props();
</script>

<section class="meta" data-testid="item-meta-panel">
  {#if item}
    <h3>Item Details</h3>
    <dl>
      <dt>Filename</dt><dd>{item.filename}</dd>
      <dt>SHA-256</dt><dd>{item.sha256}</dd>
      <dt>Size</dt><dd>{item.size_bytes} bytes</dd>
      <dt>Account</dt><dd>{item.account ?? 'n/a'}</dd>
      <dt>OneDrive ID</dt><dd>{item.onedrive_id ?? 'n/a'}</dd>
    </dl>
  {:else}
    <p>No item selected.</p>
  {/if}
</section>

<style>
  .meta {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
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
</style>
