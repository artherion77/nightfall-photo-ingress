<script lang="ts">
  import StatusBadge from '$lib/components/common/StatusBadge.svelte';

  interface Subsystem {
    ok?: boolean;
    message?: string;
  }

  interface Props {
    health: {
      polling_ok: Subsystem;
      auth_ok: Subsystem;
      registry_ok: Subsystem;
      disk_ok: Subsystem;
    };
  }

  let { health }: Props = $props();

  function statusFor(item: Subsystem) {
    return item?.ok ? 'ok' : 'error';
  }
</script>

<div class="health-bar" data-testid="health-bar">
  <div class="health-legend">
    <span class="legend-label">Health Status:</span>
    <div class="health-scale" aria-label="Health status legend">
      <span class="scale-item"><span class="scale-dot scale-dot--perfect" aria-hidden="true"></span><span>Perfect</span></span>
      <span class="scale-item"><span class="scale-dot scale-dot--good" aria-hidden="true"></span><span>Good</span></span>
      <span class="scale-item"><span class="scale-dot scale-dot--degrading" aria-hidden="true"></span><span>Degrading</span></span>
      <span class="scale-item"><span class="scale-dot scale-dot--warning" aria-hidden="true"></span><span>Warning</span></span>
      <span class="scale-item"><span class="scale-dot scale-dot--error" aria-hidden="true"></span><span>Error/Issue</span></span>
    </div>
  </div>
  <div class="health-gradient" aria-hidden="true"></div>
  <div class="health-badges">
    <StatusBadge status={statusFor(health.polling_ok)} label="Polling" />
    <StatusBadge status={statusFor(health.auth_ok)} label="OneDrive Auth" />
    <StatusBadge status={statusFor(health.registry_ok)} label="Registry Integrity" />
    <StatusBadge status={statusFor(health.disk_ok)} label="Disk Usage" />
  </div>
</div>

<style>
  .health-bar {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  .health-legend {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .legend-label {
    font-size: var(--text-sm);
    font-weight: var(--text-md-weight);
    line-height: var(--text-sm-line-height);
    color: var(--text-secondary);
  }

  .health-scale {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .scale-item {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    color: var(--text-secondary);
    font-size: var(--text-sm);
    line-height: var(--text-sm-line-height);
    white-space: nowrap;
  }

  .scale-dot {
    width: 11px;
    height: 11px;
    border-radius: 999px;
    display: inline-block;
  }

  .scale-dot--perfect {
    background: #00b3a4;
  }

  .scale-dot--good {
    background: #27b36a;
  }

  .scale-dot--degrading {
    background: #8dcf52;
  }

  .scale-dot--warning {
    background: #ffb400;
  }

  .scale-dot--error {
    background: #e5484d;
  }

  .health-gradient {
    width: 100%;
    height: var(--space-2);
    border-radius: var(--radius-full);
    background: linear-gradient(90deg, #00b3a4 0%, #ffb400 50%, #e5484d 100%);
  }

  .health-badges {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }
</style>
