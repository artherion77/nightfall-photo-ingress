<script>
  import '../styles/reset.css';
  import '$lib/tokens/tokens.css';
  import AppHeader from '$lib/components/layout/AppHeader.svelte';
  import AppFooter from '$lib/components/layout/AppFooter.svelte';
  import { health } from '$lib/stores/health.svelte';

  let { children } = $props();

  $effect(() => {
    health.connect();
    return () => {
      health.disconnect();
    };
  });
</script>

<div class="app-shell">
  <AppHeader />
  <main>
    {@render children?.()}
  </main>
  <AppFooter />
</div>

<style>
  .app-shell {
    min-height: 100vh;
    display: grid;
    grid-template-rows: auto 1fr auto;
    background: var(--surface-base);
    color: var(--text-primary);
  }

  main {
    padding: var(--space-5);
    min-height: 0;
  }
</style>
