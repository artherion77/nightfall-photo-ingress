<script lang="ts">
  import type { ComponentProps } from 'svelte';

  interface Props {
    status: 'ok' | 'warning' | 'error' | 'unknown';
    label: string;
  }

  let { status, label }: Props = $props();

  const statusColors = {
    ok: 'var(--status-ok)',
    warning: 'var(--status-warning)',
    error: 'var(--status-error)',
    unknown: 'var(--status-unknown)'
  };
</script>

<div class="status-badge" style="--status-color: {statusColors[status]};">
  <span class="dot"></span>
  <span class="label">{label}</span>
</div>

<style>
  .status-badge {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-sm);
    color: var(--text-secondary);
  }

  .dot {
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background-color: var(--status-color);
    flex-shrink: 0;
  }

  .label {
    white-space: nowrap;
  }
</style>
