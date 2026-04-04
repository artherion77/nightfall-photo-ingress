<script lang="ts">
  import LoadMoreButton from '$lib/components/common/LoadMoreButton.svelte';
  import EmptyState from '$lib/components/common/EmptyState.svelte';
  import AuditEventItem from './AuditEvent.svelte';
  import type { AuditEvent as ApiAuditEvent } from '$lib/api/audit';

  interface Props {
    events: ApiAuditEvent[];
    loading?: boolean;
    hasMore: boolean;
    onLoadMore: () => void;
  }

  let { events, loading = false, hasMore, onLoadMore }: Props = $props();
</script>

<section class="timeline" data-testid="audit-timeline">
  {#if events.length === 0}
    <EmptyState message="No audit events found." />
  {:else}
    <ul>
      {#each events as event}
        <AuditEventItem {event} />
      {/each}
    </ul>
    <LoadMoreButton {loading} {hasMore} onLoadMore={onLoadMore} />
  {/if}
</section>

<style>
  .timeline {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }
</style>
