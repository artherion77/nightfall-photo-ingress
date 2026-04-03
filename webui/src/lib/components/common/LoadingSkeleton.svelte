<script lang="ts">
  interface Props {
    height?: string;
    width?: string;
  }

  let { height = '100px', width = '100%' }: Props = $props();
</script>

<div class="loading-skeleton" style="--skeleton-height: {height}; --skeleton-width: {width};">
</div>

<style>
  .loading-skeleton {
    width: var(--skeleton-width);
    height: var(--skeleton-height);
    background: linear-gradient(
      90deg,
      var(--surface-card) 0%,
      var(--surface-hover) 50%,
      var(--surface-card) 100%
    );
    background-size: 200% 100%;
    animation: shimmer 2s ease-in-out infinite;
    border-radius: var(--radius-md);
  }

  @keyframes shimmer {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }
</style>
