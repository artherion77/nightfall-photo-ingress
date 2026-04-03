<script lang="ts">
  interface EventItem {
    id: number;
    action: string;
    ts: string;
    sha256?: string;
  }

  interface Props {
    events: EventItem[];
  }

  let { events }: Props = $props();
</script>

<section class="audit-preview" data-testid="audit-preview">
  <div class="header">
    <h2>Recent Audit Events</h2>
    <a href="/audit">View all</a>
  </div>

  {#if events.length === 0}
    <p>No audit events.</p>
  {:else}
    <ul>
      {#each events as event}
        <li>
          <strong>{event.action}</strong>
          <span>{event.sha256 ? event.sha256.slice(0, 12) : 'n/a'}</span>
          <time>{event.ts}</time>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .audit-preview {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-3);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  li {
    display: grid;
    grid-template-columns: 120px 1fr auto;
    gap: var(--space-3);
    font-size: var(--text-sm);
  }
</style>
