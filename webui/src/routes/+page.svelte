<script lang="ts">
	import AuditPreview from '$lib/components/dashboard/AuditPreview.svelte';
	import HealthBar from '$lib/components/dashboard/HealthBar.svelte';
	import KpiGrid from '$lib/components/dashboard/KpiGrid.svelte';
	import PollRuntimeChart from '$lib/components/dashboard/PollRuntimeChart.svelte';

	let { data } = $props();

	let kpis = $derived({
		pending_count: data.staging?.total ?? 0,
		accepted_today: 0,
		rejected_today: 0,
		live_photo_pairs: 0,
		last_poll_duration_s: 0
	});
</script>

<section class="dashboard" data-testid="dashboard-page">
	<h1>Dashboard</h1>
	<KpiGrid {kpis} thresholds={data.config?.kpi_thresholds ?? {}} />
	<HealthBar health={data.health} />
	<PollRuntimeChart values={[kpis.last_poll_duration_s]} />
	<AuditPreview events={data.audit?.events ?? []} />
</section>

<style>
	.dashboard {
		display: grid;
		gap: var(--space-4);
	}
</style>
