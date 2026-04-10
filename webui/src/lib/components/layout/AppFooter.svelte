<script lang="ts">
  import { health } from '$lib/stores/health.svelte';
  import { stagingQueue } from '$lib/stores/stagingQueue.svelte';
  import StatusBadge from '../common/StatusBadge.svelte';

  // ----- Footer state machine -----

  type FooterMode =
    | 'INITIALIZING'
    | 'HEALTH_UNAVAILABLE'
    | 'POLL_IN_PROGRESS'
    | 'NEVER_POLLED'
    | 'TIMER_STOPPED_NEVER_POLLED'
    | 'POLLED_TIMER_RUNNING'
    | 'POLLED_TIMER_STOPPED'
    | 'POLLED_UNKNOWN';

  function getMode(): FooterMode {
    if ($health.error) return 'HEALTH_UNAVAILABLE';
    if (pollInProgress || $health.poller_status === 'in_progress') return 'POLL_IN_PROGRESS';
    if ($health.last_poll_at === undefined) return 'INITIALIZING';
    if ($health.last_poll_at === null) {
      return $health.poller_status === 'timer_running'
        ? 'NEVER_POLLED'
        : 'TIMER_STOPPED_NEVER_POLLED';
    }
    if ($health.poller_status === 'timer_running') return 'POLLED_TIMER_RUNNING';
    if ($health.poller_status === 'timer_stopped') return 'POLLED_TIMER_STOPPED';
    return 'POLLED_UNKNOWN';
  }

  // ----- Time formatting -----

  function formatPastTime(iso: string | null | undefined): string {
    if (iso == null) return 'never';
    const date = new Date(iso);
    if (isNaN(date.getTime())) return 'unknown';

    const now = new Date();
    const diffS = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffS < 60) return 'just now';
    if (diffS < 3600) return `${Math.floor(diffS / 60)}m ago`;
    if (diffS < 86400) return `${Math.floor(diffS / 3600)}h ago`;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const weekAgo = new Date(today);
    weekAgo.setDate(today.getDate() - 7);

    const hhmm = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

    if (date >= today) return `today at ${hhmm}`;
    if (date >= yesterday) return `yesterday at ${hhmm}`;
    if (date >= weekAgo) {
      const day = date.toLocaleDateString(undefined, { weekday: 'short' });
      return `${day} at ${hhmm}`;
    }
    return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function formatFutureTime(iso: string | null | undefined): string {
    if (iso == null) return '';
    const date = new Date(iso);
    if (isNaN(date.getTime())) return '';

    const now = new Date();
    const diffS = Math.floor((date.getTime() - now.getTime()) / 1000);

    if (diffS <= 0) return 'soon';
    if (diffS < 3600) return `in ${Math.floor(diffS / 60)}m`;
    if (diffS < 86400) return `in ${Math.floor(diffS / 3600)}h`;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    const dayAfter = new Date(today);
    dayAfter.setDate(today.getDate() + 2);

    const hhmm = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    if (date < tomorrow) return `today at ${hhmm}`;
    if (date < dayAfter) return `tomorrow at ${hhmm}`;
    return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  // ----- Manual poll -----

  let pollInProgress = $state(false);
  let pollError = $state(false);
  let pollErrorTimer: ReturnType<typeof setTimeout> | null = null;

  async function handleManualPoll() {
    if (pollInProgress || $health.poller_status === 'in_progress') return;
    pollError = false;
    pollInProgress = true;
    try {
      await health.triggerPoll();
      await stagingQueue.loadPage();
    } catch (_err) {
      pollError = true;
      if (pollErrorTimer !== null) clearTimeout(pollErrorTimer);
      pollErrorTimer = setTimeout(() => {
        pollError = false;
      }, 4000);
    } finally {
      pollInProgress = false;
    }
  }

  $effect(() => {
    return () => {
      if (pollErrorTimer !== null) clearTimeout(pollErrorTimer);
    };
  });

  function getRegistryStatus() {
    return $health.registry_ok?.ok ? 'ok' : 'error';
  }
</script>

<footer class="app-footer">
  <div class="footer-left">
    <span class="version">v0.1.0</span>
  </div>

  <div class="footer-center">
    {#if getMode() === 'INITIALIZING'}
      <span class="poll-info">Last poll: loading…</span>

    {:else if getMode() === 'HEALTH_UNAVAILABLE'}
      <span class="poll-info poll-info--error" role="status">Health check unavailable</span>

    {:else if getMode() === 'POLL_IN_PROGRESS'}
      <span class="poll-info poll-info--active" role="status">
        <span class="spinner" aria-hidden="true"></span>
        Poll in progress…
      </span>

    {:else if getMode() === 'NEVER_POLLED'}
      <span class="poll-info">Last poll: never</span>
      {#if $health.next_poll_at && formatFutureTime($health.next_poll_at)}
        <span class="poll-next">Next: {formatFutureTime($health.next_poll_at)}</span>
      {/if}

    {:else if getMode() === 'TIMER_STOPPED_NEVER_POLLED'}
      <span class="poll-info poll-info--warning">Last poll: never</span>
      <span class="poll-badge poll-badge--stopped">⚠ Timer stopped</span>

    {:else if getMode() === 'POLLED_TIMER_RUNNING'}
      <span class="poll-info" title={$health.last_poll_at ?? undefined}>
        Last poll: {formatPastTime($health.last_poll_at)}
      </span>
      {#if $health.next_poll_at && formatFutureTime($health.next_poll_at)}
        <span class="poll-next">Next: {formatFutureTime($health.next_poll_at)}</span>
      {/if}

    {:else if getMode() === 'POLLED_TIMER_STOPPED'}
      <span class="poll-info poll-info--warning" title={$health.last_poll_at ?? undefined}>
        Last poll: {formatPastTime($health.last_poll_at)}
      </span>
      <span class="poll-badge poll-badge--stopped">⚠ Timer stopped</span>

    {:else}
      <!-- POLLED_UNKNOWN -->
      <span class="poll-info" title={$health.last_poll_at ?? undefined}>
        Last poll: {formatPastTime($health.last_poll_at)}
      </span>
    {/if}

    {#if pollError}
      <span class="poll-info poll-info--error" role="alert">Poll trigger failed</span>
    {/if}
  </div>

  <div class="footer-right">
    <div class="footer-right-inner">
      <button
        class="poll-button"
        class:poll-button--busy={pollInProgress || $health.poller_status === 'in_progress'}
        disabled={pollInProgress || $health.poller_status === 'in_progress' || !!$health.error}
        onclick={handleManualPoll}
        title="Trigger an immediate poll cycle"
        aria-label="Poll now"
      >
        {#if pollInProgress}
          <span class="spinner spinner--sm" aria-hidden="true"></span>
          Polling…
        {:else}
          Poll now
        {/if}
      </button>
      <StatusBadge status={getRegistryStatus()} label="Registry" />
    </div>
  </div>
</footer>

<style>
  .app-footer {
    background-color: var(--surface-raised);
    border-top: 1px solid var(--border-default);
    padding: var(--space-4);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .footer-left,
  .footer-center,
  .footer-right {
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;
  }

  .footer-left {
    justify-content: flex-start;
  }

  .footer-right {
    justify-content: flex-end;
  }

  .footer-right-inner {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .footer-center {
    gap: var(--space-3);
    flex-wrap: wrap;
  }

  .version {
    font-family: var(--font-family-mono);
    font-size: var(--text-mono-sm);
  }

  .poll-info {
    font-size: var(--text-sm);
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  .poll-info--error {
    color: var(--status-error);
  }

  .poll-info--warning {
    color: var(--status-warning);
  }

  .poll-info--active {
    color: var(--status-info);
  }

  .poll-next {
    font-size: var(--text-sm);
    color: var(--text-muted);
  }

  .poll-badge {
    font-size: var(--text-xs);
    padding: 1px var(--space-2);
    border-radius: var(--radius-sm);
  }

  .poll-badge--stopped {
    color: var(--status-warning);
    border: 1px solid var(--status-warning);
  }

  /* Spinner */
  .spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  .spinner--sm {
    width: 10px;
    height: 10px;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Poll button */
  .poll-button {
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-default);
    background: var(--surface-raised);
    color: var(--text-secondary);
    font-size: var(--text-sm);
    font-family: var(--font-family-base);
    cursor: pointer;
    transition: all var(--duration-default) var(--easing-default);
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  .poll-button:hover:not(:disabled) {
    background: var(--surface-hover, var(--surface-raised));
    color: var(--text-primary);
    border-color: var(--text-muted);
  }

  .poll-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .poll-button--busy {
    color: var(--status-info);
    border-color: var(--status-info);
  }
</style>

