<script lang="ts">
  import StatusBadge from '../common/StatusBadge.svelte';
  import { page } from '$app/stores';
  import { health } from '$lib/stores/health.svelte';

  const pages = [
    { path: '/', label: 'Dashboard' },
    { path: '/staging', label: 'Staging' },
    { path: '/audit', label: 'Audit' },
    { path: '/blocklist', label: 'Blocklist' },
    { path: '/settings', label: 'Settings' }
  ];

  function getHealthLabel() {
    if ($health.error) return 'error';
    if (!$health.polling_ok?.ok || !$health.auth_ok?.ok || !$health.registry_ok?.ok || !$health.disk_ok?.ok) {
      return 'warning';
    }
    return 'ok';
  }
</script>

<header class="app-header">
  <div class="header-left">
    <div class="logo">📸</div>
    <nav class="nav-tabs">
      {#each pages as p}
        <a
          href={p.path}
          class="nav-tab"
          class:active={$page.url.pathname === p.path}
        >
          {p.label}
        </a>
      {/each}
    </nav>
  </div>
  <div class="header-right">
    <StatusBadge status={getHealthLabel()} label="System" />
  </div>
</header>

<style>
  .app-header {
    background-color: var(--surface-raised);
    border-bottom: 1px solid var(--border-default);
    padding: var(--space-4);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-5);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    flex: 1;
  }

  .logo {
    font-size: 24px;
    flex-shrink: 0;
  }

  .nav-tabs {
    display: flex;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .nav-tab {
    text-decoration: none;
    color: var(--text-secondary);
    font-size: var(--text-base);
    padding: var(--space-2) var(--space-3);
    border-bottom: 2px solid transparent;
    transition: all var(--duration-default) var(--easing-default);
    cursor: pointer;
  }

  .nav-tab:hover {
    color: var(--text-primary);
  }

  .nav-tab.active {
    color: var(--text-primary);
    border-bottom-color: var(--action-primary);
  }

  .header-right {
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }
</style>
