<script lang="ts">
  import type { AuditEvent as ApiAuditEvent } from '$lib/api/audit';
  import { relativeTimeFromIso } from '$lib/utils/relativeTime';

  interface Props {
    event: ApiAuditEvent;
    variant?: 'timeline' | 'preview';
  }

  let { event, variant = 'timeline' }: Props = $props();

  function shortSha(value: string | null | undefined): string {
    if (!value) return 'n/a';
    return `${value.slice(0, 12)}...`;
  }

  type AuditVisualState = 'accepted' | 'duplicate' | 'rejected' | 'deleted' | 'default';

  function visualState(action: string): AuditVisualState {
    const normalized = action.toLowerCase();
    if (normalized.includes('accept')) return 'accepted';
    if (normalized.includes('duplicate')) return 'duplicate';
    if (normalized.includes('reject')) return 'rejected';
    if (normalized.includes('discard') || normalized.includes('trash') || normalized.includes('delete')) return 'deleted';
    return 'default';
  }

  function actionLabel(action: string): string {
    const state = visualState(action);
    if (state === 'accepted') return 'Accepted';
    if (state === 'duplicate') return 'Duplicate Skipped';
    if (state === 'rejected') return 'Rejected';
    if (state === 'deleted') return 'Sent to Trash';
    return action.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
  }

  function actionColor(action: string): string {
    const state = visualState(action);
    if (state === 'accepted') return 'var(--action-accept)';
    if (state === 'duplicate') return 'var(--status-info)';
    if (state === 'rejected') return 'var(--action-reject)';
    if (state === 'deleted') return 'var(--text-muted)';
    return 'var(--text-secondary)';
  }

  const state = $derived(visualState(event.action));
  const displayFilename = $derived(event.filename?.trim() || 'filename unavailable');
  const displayAction = $derived(actionLabel(event.action));
  const displayTime = $derived(relativeTimeFromIso(event.ts));
  const tooltip = $derived.by(() => {
    const lines = [
      `filename: ${displayFilename}`,
      `action: ${event.action}`,
      `timestamp: ${event.ts}`,
    ];
    if (event.account_name) {
      lines.push(`account: ${event.account_name}`);
    }
    if (event.client_ip) {
      lines.push(`client_ip: ${event.client_ip}`);
    }
    return lines.join('\n');
  });
</script>

{#if variant === 'preview'}
  <li class="event event--preview" data-testid="audit-event" title={tooltip}>
    <span class="status-icon" style={`--event-color: ${actionColor(event.action)}`} aria-hidden="true">
      {#if state === 'accepted'}
        <svg viewBox="0 0 24 24" focusable="false" class="icon accepted">
          <circle cx="12" cy="12" r="6" fill="var(--status-ok)"></circle>
        </svg>
      {:else if state === 'duplicate'}
        <svg viewBox="0 0 24 24" focusable="false" class="icon duplicate">
          <circle cx="12" cy="12" r="6" fill="none" stroke="var(--status-info)" stroke-width="2"></circle>
        </svg>
      {:else if state === 'rejected'}
        <svg viewBox="0 0 24 24" focusable="false" class="icon rejected">
          <circle cx="12" cy="12" r="7" fill="none" stroke="var(--action-reject)" stroke-width="1.8"></circle>
          <path d="M9.3 9.3l5.4 5.4M14.7 9.3l-5.4 5.4" fill="none" stroke="var(--action-reject)" stroke-width="2" stroke-linecap="round"></path>
        </svg>
      {:else if state === 'deleted'}
        <svg viewBox="0 0 24 24" focusable="false" class="icon deleted">
          <path d="M8 8h8l-.6 9.2a1.4 1.4 0 0 1-1.4 1.3h-4a1.4 1.4 0 0 1-1.4-1.3L8 8z" fill="none" stroke="var(--text-muted)" stroke-width="1.8" stroke-linejoin="round"></path>
          <path d="M9.2 8V6.6c0-.6.5-1.1 1.1-1.1h3.4c.6 0 1.1.5 1.1 1.1V8M6.8 8h10.4" fill="none" stroke="var(--text-muted)" stroke-width="1.8" stroke-linecap="round"></path>
        </svg>
      {:else}
        <svg viewBox="0 0 24 24" focusable="false" class="icon default">
          <circle cx="12" cy="12" r="5" fill="var(--status-unknown)"></circle>
        </svg>
      {/if}
    </span>

    <div class="event-main">
      <div class="event-line">
        <span class="filename" title={displayFilename}>{displayFilename}</span>
        <span class="action" style={`--action-color: ${actionColor(event.action)};`}>{displayAction}</span>
        <time class="relative-time" datetime={event.ts}>{displayTime}</time>
      </div>
      {#if event.account_name || event.client_ip}
        <div class="event-meta">
          {#if event.account_name}
            <span class="meta-item">{event.account_name}</span>
          {/if}
          {#if event.client_ip}
            <span class="meta-item">{event.client_ip}</span>
          {/if}
        </div>
      {/if}
    </div>
  </li>
{:else}
  <li class="event" data-testid="audit-event">
    <span class="message">{event.description || event.action}</span>
    <span class="sep">|</span>
    {#if event.filename}
      <span class="filename">{event.filename}</span>
    {:else}
      <span class="filename filename--muted">filename unavailable</span>
    {/if}
    <span class="sep">|</span>
    <span class="account">{event.account_name ?? 'account unavailable'}</span>
    <span class="sep">|</span>
    <span class="action-code">{event.action}</span>
    <span class="sep">|</span>
    <span class="sha">{shortSha(event.sha256)}</span>
    <span class="sep">|</span>
    <span class="actor">{event.actor ?? 'api'}</span>
    <span class="sep">|</span>
    <time>{event.ts}</time>
  </li>
{/if}

<style>
  .event {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: var(--text-sm);
  }

  .event--preview {
    align-items: flex-start;
    white-space: normal;
    gap: var(--space-3);
  }

  .status-icon {
    width: var(--space-4);
    height: var(--space-4);
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .status-icon :global(svg) {
    width: 100%;
    height: 100%;
    display: block;
  }

  .event-main {
    min-width: 0;
    flex: 1 1 auto;
    display: grid;
    gap: var(--space-1);
  }

  .event-line {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
  }

  .event-line .filename {
    font-size: var(--text-base);
    font-weight: var(--text-md-weight);
    line-height: var(--text-base-line-height);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .action {
    color: var(--action-color);
    font-size: var(--text-sm);
    font-weight: var(--text-md-weight);
    white-space: nowrap;
    flex: 0 0 auto;
  }

  .relative-time {
    margin-left: auto;
    color: var(--text-secondary);
    font-size: var(--text-sm);
    white-space: nowrap;
    flex: 0 0 auto;
  }

  .event-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .meta-item {
    color: var(--text-muted);
    font-size: var(--text-xs);
    line-height: var(--text-xs-line-height);
  }

  .message {
    color: var(--text-primary);
    font-weight: var(--text-md-weight);
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }

  .filename {
    color: var(--text-primary);
  }

  .filename--muted {
    color: var(--text-secondary);
  }

  .sep {
    color: var(--border-default);
  }

  .sha,
  .action-code,
  .account,
  .actor,
  time {
    color: var(--text-secondary);
    flex: 0 0 auto;
  }
</style>
