<script lang="ts">
  import AuditEventItem from '$lib/components/audit/AuditEvent.svelte';
  import type { AuditEvent as EventItem } from '$lib/api/audit';

  interface Props {
    events: EventItem[];
  }

  let { events }: Props = $props();
  const MAX_PREVIEW_ITEMS = 6;
  const previewEvents = $derived(events.slice(0, MAX_PREVIEW_ITEMS));
</script>

<section class="audit-preview" data-testid="audit-preview">
  <div class="header">
    <h2>Recent Audit Events</h2>
    <a href="/audit">View all</a>
  </div>

  {#if previewEvents.length === 0}
    <p>No audit events.</p>
  {:else}
    <ul>
      {#each previewEvents as event}
        <AuditEventItem {event} variant="preview" />
      {/each}
    </ul>
  {/if}
</section>

<style>
  .audit-preview {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-left: 3px solid var(--action-primary);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-3);
  }

  .header h2 {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: var(--text-lg-weight);
    line-height: var(--text-lg-line-height);
    color: var(--text-primary);
    padding-bottom: var(--space-1);
    border-bottom: 2px solid var(--color-accent-teal);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
  }
</style>
