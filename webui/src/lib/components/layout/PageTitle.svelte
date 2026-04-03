<script lang="ts">
  interface Props {
    title: string;
    subtitle?: string;
  }

  let { title, subtitle }: Props = $props();
</script>

<div class="page-title">
  <h1 class="title">{title}</h1>
  {#if subtitle}
    <p class="subtitle">{subtitle}</p>
  {/if}
</div>

<style>
  .page-title {
    margin-bottom: var(--space-6);
  }

  .title {
    margin: 0 0 var(--space-2) 0;
    font-size: var(--text-2xl);
    font-weight: var(--text-2xl-weight);
    color: var(--text-primary);
    line-height: var(--text-2xl-line-height);
  }

  .subtitle {
    margin: 0;
    font-size: var(--text-base);
    color: var(--text-secondary);
    line-height: var(--text-base-line-height);
  }
</style>
