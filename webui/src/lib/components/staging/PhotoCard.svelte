<script lang="ts">
  interface Props {
    item: {
      sha256: string;
      filename: string;
      account?: string;
      first_seen_at?: string;
    };
    active?: boolean;
  }

  let { item, active = false }: Props = $props();
</script>

<article class="photo-card" class:active data-testid="photo-card">
  <div class="thumb">IMG</div>
  <h3>{item.filename}</h3>
  <p>{item.sha256.slice(0, 16)}...</p>
  <p>{item.account ?? 'unknown account'}</p>
  <p>{item.first_seen_at ?? ''}</p>
</article>

<style>
  .photo-card {
    min-width: 220px;
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

  .thumb {
    width: 100%;
    height: 120px;
    border-radius: var(--radius-md);
    background: var(--surface-hover);
    display: grid;
    place-items: center;
    margin-bottom: var(--space-3);
  }

  h3 {
    margin: 0 0 var(--space-2) 0;
    font-size: var(--text-base);
  }

  p {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }
</style>
