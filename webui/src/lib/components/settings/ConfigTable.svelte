<script lang="ts">
  interface Props {
    config: Record<string, unknown>;
  }

  let { config }: Props = $props();

  let entries = $derived(Object.entries(config).filter(([key]) => key !== 'loading' && key !== 'error'));
</script>

<section class="config-table" data-testid="config-table">
  <table>
    <thead>
      <tr><th>Key</th><th>Value</th></tr>
    </thead>
    <tbody>
      {#each entries as [key, value]}
        <tr>
          <td>{key}</td>
          <td>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</section>

<style>
  .config-table {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
  }

  th,
  td {
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border-subtle);
    text-align: left;
  }

  th {
    color: var(--text-secondary);
  }
</style>
