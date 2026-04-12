<script lang="ts">
  interface Props {
    status: 'ok' | 'warning' | 'error' | 'unknown';
    label: string;
    icon?: 'auto' | 'ok' | 'warning' | 'error' | 'unknown' | 'auth';
  }

  let { status, label, icon = 'auto' }: Props = $props();

  const statusColors: Record<Props['status'], string> = {
    ok: 'var(--status-ok)',
    warning: 'var(--status-warning)',
    error: 'var(--status-error)',
    unknown: 'var(--status-unknown)'
  };

  type IconType = Exclude<Props['icon'], 'auto'>;

  const resolvedIcon = $derived<IconType>(icon === 'auto' ? status : icon);
</script>

<div class="status-badge" style="--status-color: {statusColors[status]};">
  <span class="icon" aria-hidden="true">
    {#if resolvedIcon === 'ok'}
      <svg viewBox="0 0 24 24" focusable="false">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"></circle>
        <path d="M8.2 12.3l2.6 2.6 5.2-5.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
      </svg>
    {:else if resolvedIcon === 'warning'}
      <svg viewBox="0 0 24 24" focusable="false">
        <path d="M12 4l8.2 14.2H3.8L12 4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"></path>
        <path d="M12 9v4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
        <circle cx="12" cy="16.7" r="1" fill="currentColor"></circle>
      </svg>
    {:else if resolvedIcon === 'error'}
      <svg viewBox="0 0 24 24" focusable="false">
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"></circle>
        <path d="M9 9l6 6M15 9l-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path>
      </svg>
    {:else if resolvedIcon === 'auth'}
      <svg viewBox="0 0 24 24" focusable="false">
        <path d="M7.2 17.8h9.2c2 0 3.6-1.5 3.6-3.4 0-1.8-1.3-3.2-3.1-3.4-.5-2.6-2.8-4.5-5.5-4.5-2.8 0-5.2 2-5.5 4.8-1.8.2-3.1 1.7-3.1 3.4 0 1.9 1.6 3.5 3.6 3.5z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path>
        <path d="M9.8 13.8l1.7 1.7 3-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
      </svg>
    {:else}
      <svg viewBox="0 0 24 24" focusable="false">
        <circle cx="12" cy="12" r="4" fill="currentColor"></circle>
      </svg>
    {/if}
  </span>
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

  .icon {
    width: var(--space-4);
    height: var(--space-4);
    color: var(--status-color);
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .icon :global(svg) {
    width: 100%;
    height: 100%;
    display: block;
  }

  .label {
    white-space: nowrap;
  }
</style>
