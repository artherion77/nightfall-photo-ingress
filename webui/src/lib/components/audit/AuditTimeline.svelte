<script lang="ts">
  import { onDestroy } from 'svelte';
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
  let sentinel: HTMLDivElement | null = $state(null);
  let observer: IntersectionObserver | null = $state(null);

  function reconnectObserver() {
    if (!observer) {
      return;
    }
    observer.disconnect();
    if (sentinel && hasMore) {
      observer.observe(sentinel);
    }
  }

  $effect(() => {
    reconnectObserver();
  });

  $effect(() => {
    if (!observer) {
      observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            onLoadMore();
          }
        },
        {
          root: null,
          rootMargin: '0px 0px 220px 0px',
          threshold: 0,
        },
      );
      reconnectObserver();
    }
  });

  onDestroy(() => {
    observer?.disconnect();
    observer = null;
  });
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
    {#if hasMore}
      <div class="sentinel" bind:this={sentinel} data-testid="audit-timeline-sentinel" aria-hidden="true"></div>
      <p class="scroll-hint" data-testid="audit-scroll-hint">
        {#if loading}
          Loading more events...
        {:else}
          Scroll to load more
        {/if}
      </p>
    {:else}
      <p class="end-marker" data-testid="audit-end-marker">End of timeline</p>
    {/if}
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

  .sentinel {
    height: 1px;
    width: 100%;
  }

  .scroll-hint,
  .end-marker {
    margin: var(--space-3) 0 0;
    color: var(--text-secondary);
    font-size: var(--text-xs);
    text-align: center;
  }
</style>
