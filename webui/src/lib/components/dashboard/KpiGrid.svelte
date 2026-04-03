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
  <KpiCard label="Pending" value={kpis.pending_count} thresholds={{ warning: thresholds.pending_warning ?? 50, error: thresholds.pending_error ?? 100 }} />
  <KpiCard label="Accepted Today" value={kpis.accepted_today} />
  <KpiCard label="Rejected Today" value={kpis.rejected_today} />
  <KpiCard label="Live Photo Pairs" value={kpis.live_photo_pairs} />
  <KpiCard label="Last Poll (s)" value={kpis.last_poll_duration_s} />
</div>

<style>
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: var(--space-4);
  }
</style>
