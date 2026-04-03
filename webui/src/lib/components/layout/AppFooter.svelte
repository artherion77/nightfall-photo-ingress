<script lang="ts">
  import { health } from '$lib/stores/health.svelte';
  import StatusBadge from '../common/StatusBadge.svelte';

  function formatTime(iso?: string) {
    if (!iso) return 'never';
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);

    if (diffSecs < 60) return 'just now';
    if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)}m ago`;
    if (diffSecs < 86400) return `${Math.floor(diffSecs / 3600)}h ago`;
    return date.toLocaleString();
  }

  function getRegistryStatus() {
    return health.registry_ok ? 'ok' : 'error';
  }
</script>

<footer class="app-footer">
  <div class="footer-left">
    <span class="version">v0.1.0</span>
  </div>
  <div class="footer-center">
    <span class="last-poll">Last poll: {formatTime(health.last_updated_at)}</span>
  </div>
  <div class="footer-right">
    <StatusBadge status={getRegistryStatus()} label="Registry" />
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

  .version {
    font-family: var(--font-family-mono);
    font-size: var(--text-mono-sm);
  }

  .last-poll {
    font-size: var(--text-sm);
  }
</style>
