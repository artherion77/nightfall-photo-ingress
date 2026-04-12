<script lang="ts">
  import KpiCard from '$lib/components/common/KpiCard.svelte';

  interface Props {
    kpis: {
      pending_count: number;
      accepted_today: number;
      rejected_today: number;
      live_photo_pairs: number;
      last_poll_duration_s: number;
    };
    thresholds?: Record<string, number>;
  }

  let { kpis, thresholds = {} }: Props = $props();
</script>

<div class="kpi-grid" data-testid="kpi-grid">
  <div class="tile-r1"><KpiCard label="Pending in Staging" value={kpis.pending_count} thresholds={{ warning: thresholds.pending_warning ?? 50, error: thresholds.pending_error ?? 100 }} /></div>
  <div class="tile-r1"><KpiCard label="Accepted Today" value={kpis.accepted_today} /></div>
  <div class="tile-r1"><KpiCard label="Rejected Today" value={kpis.rejected_today} /></div>
  <div class="tile-r2"><KpiCard label="Live Photo Pairs Detected" value={kpis.live_photo_pairs} /></div>
  <div class="tile-r2"><KpiCard label="Last Poll Duration" value={kpis.last_poll_duration_s} /></div>
</div>

<style>
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: var(--space-4);
  }

  .tile-r1 {
    grid-column: span 2;
  }

  .tile-r2 {
    grid-column: span 3;
  }
</style>
