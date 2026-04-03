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
  <StatusBadge status={statusFor(health.polling_ok)} label="Polling" />
  <StatusBadge status={statusFor(health.auth_ok)} label="Auth" />
  <StatusBadge status={statusFor(health.registry_ok)} label="Registry" />
  <StatusBadge status={statusFor(health.disk_ok)} label="Disk" />
</div>

<style>
  .health-bar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    padding: var(--space-3);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }
</style>
