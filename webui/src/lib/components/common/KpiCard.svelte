<script lang="ts">
  interface Thresholds {
    warning: number;
    error: number;
  }

  interface Props {
    label: string;
    value: number | string;
    status?: 'ok' | 'warning' | 'error' | 'unknown';
    thresholds?: Thresholds;
  }

  let { label, value, status = 'unknown', thresholds }: Props = $props();

  // Determine status from value and thresholds if not explicitly provided
  let computedStatus = $derived(() => {
    if (status !== 'unknown') return status;
    if (typeof value !== 'number' || !thresholds) return 'unknown';
    if (value >= thresholds.error) return 'error';
    if (value >= thresholds.warning) return 'warning';
    return 'ok';
  })();

  const statusColors = {
    ok: 'var(--status-ok)',
    warning: 'var(--status-warning)',
    error: 'var(--status-error)',
    unknown: 'var(--status-unknown)'
  };
</script>

<div class="kpi-card">
  <div class="header">
    <span class="label">{label}</span>
  </div>
  <div class="value">{value}</div>
  <div class="status-bar" style="--status-color: {statusColors[computedStatus]};"></div>
</div>

<style>
  .kpi-card {
    background-color: var(--surface-card);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    box-shadow: var(--shadow-sm);
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .label {
    font-size: var(--text-sm);
    color: var(--text-secondary);
    font-weight: var(--text-sm-weight);
  }

  .value {
    font-size: var(--text-xl);
    font-weight: var(--text-xl-weight);
    color: var(--text-primary);
    line-height: var(--text-xl-line-height);
  }

  .status-bar {
    height: 3px;
    background-color: var(--status-color);
    border-radius: var(--radius-sm);
    margin-top: var(--space-2);
  }
</style>
