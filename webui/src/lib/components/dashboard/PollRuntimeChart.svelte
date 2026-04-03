<script lang="ts">
  interface Props {
    values?: number[];
  }

  let { values = [] }: Props = $props();
</script>

<div class="chart" data-testid="poll-runtime-chart">
  {#if values.length === 0}
    <p>No runtime samples yet.</p>
  {:else}
    <div class="bars">
      {#each values as value}
        <span class="bar" style={`height:${Math.max(4, value)}px`} title={`${value}s`}></span>
      {/each}
    </div>
  {/if}
</div>

<style>
  .chart {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  .bars {
    display: flex;
    align-items: end;
    gap: var(--space-2);
    min-height: 60px;
  }

  .bar {
    width: 12px;
    border-radius: var(--radius-sm);
    background: var(--action-primary);
  }
</style>
