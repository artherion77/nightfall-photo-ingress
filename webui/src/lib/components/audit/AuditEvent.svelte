<script lang="ts">
  import type { AuditEvent as ApiAuditEvent } from '$lib/api/audit';

  interface Props {
    event: ApiAuditEvent;
  }

  let { event }: Props = $props();
</script>

<li class="event" data-testid="audit-event">
  <span class="action">{event.action}</span>
  <span class="sha">{event.sha256 ? `${event.sha256.slice(0, 12)}...` : 'n/a'}</span>
  <span class="actor">{event.actor ?? 'api'}</span>
  <time>{event.ts}</time>
</li>

<style>
  .event {
    display: grid;
    grid-template-columns: 120px 1fr 80px auto;
    gap: var(--space-3);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: var(--text-sm);
  }

  .action {
    color: var(--text-primary);
    font-weight: var(--text-md-weight);
  }

  .sha,
  .actor,
  time {
    color: var(--text-secondary);
  }
</style>
