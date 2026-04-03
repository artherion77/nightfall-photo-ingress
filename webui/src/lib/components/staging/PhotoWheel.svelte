<script lang="ts">
  import EmptyState from '$lib/components/common/EmptyState.svelte';
  import PhotoCard from './PhotoCard.svelte';

  interface Item {
    sha256: string;
    filename: string;
    account?: string;
    first_seen_at?: string;
  }

  interface Props {
    items: Item[];
    activeIndex?: number;
  }

  let { items, activeIndex = 0 }: Props = $props();
</script>

<section class="wheel" data-testid="photo-wheel">
  {#if items.length === 0}
    <EmptyState message="No pending items in staging queue." />
  {:else}
    <div class="track">
      {#each items as item, index}
        <div
          class="slot"
          style={`filter: blur(${index === activeIndex ? '0px' : index % 2 === 0 ? 'var(--wheel-blur-near)' : 'var(--wheel-blur-far)'});`}
        >
          <PhotoCard item={item} active={index === activeIndex} />
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .wheel {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    background: var(--surface-card);
    overflow-x: auto;
  }

  .track {
    display: flex;
    gap: var(--space-4);
  }

  .slot {
    transition: filter var(--duration-default) var(--easing-default);
  }
</style>
