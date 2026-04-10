<script lang="ts">
  import type { AuditEvent as ApiAuditEvent } from '$lib/api/audit';

  interface Props {
    event: ApiAuditEvent;
  }

  let { event }: Props = $props();

  function shortSha(value: string | null | undefined): string {
    if (!value) return 'n/a';
    return `${value.slice(0, 12)}...`;
  }
</script>

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
