<script lang="ts">
	import AuditPreview from '$lib/components/dashboard/AuditPreview.svelte';
	import FilterSidebar from '$lib/components/dashboard/FilterSidebar.svelte';
	import HealthBar from '$lib/components/dashboard/HealthBar.svelte';
	import KpiGrid from '$lib/components/dashboard/KpiGrid.svelte';
	import PollRuntimeChart from '$lib/components/dashboard/PollRuntimeChart.svelte';
	import {
		createFilterStore,
		deriveDashboardAccountOptions,
		deriveDashboardFileTypeOptions,
	} from '$lib/stores/filterStore';
	import type { AuditDailySummary, AuditPage } from '$lib/api/audit';
        import type { StagingPage } from '$lib/api/staging';
        import type { HealthResponse, PollHistoryEntry } from '$lib/api/health';
        import type { EffectiveConfig } from '$lib/api/config';

        interface PageData {
                staging?: StagingPage;
                audit?: AuditPage;
			auditSummary?: AuditDailySummary;
                config?: EffectiveConfig;
                health?: HealthResponse;
                pollHistory?: PollHistoryEntry[];
        }

        let { data }: { data: PageData } = $props();

	const dashboardFilterStore = createFilterStore();

	let kpis = $derived({
		pending_count: data.staging?.total ?? 0,
		accepted_today: data.auditSummary?.accepted_today ?? 0,
		rejected_today: data.auditSummary?.rejected_today ?? 0,
		live_photo_pairs: 0,
		last_poll_duration_s: data.health?.poll_duration_s ?? 0
	});

	const dashboardItems = $derived(data.staging?.items ?? []);
	const filterOptions = $derived(deriveDashboardFileTypeOptions(dashboardItems));
	const accountOptions = $derived(deriveDashboardAccountOptions(dashboardItems));
</script>

<section class="dashboard" data-testid="dashboard-page">
	<h1>Photo-Ingress Dashboard</h1>
	<div class="dashboard-layout">
		<FilterSidebar
			options={filterOptions}
			accountOptions={accountOptions}
			activeFilters={$dashboardFilterStore.activeFilters}
			activeAccounts={$dashboardFilterStore.activeAccounts}
			onToggle={(id) => dashboardFilterStore.toggle(id)}
			onToggleAccount={(account) => dashboardFilterStore.toggleAccount(account)}
			onClear={() => {
				dashboardFilterStore.clear();
				dashboardFilterStore.clearAccounts();
			}}
		/>

		<div class="dashboard-main">
			{#if data.health}
			<HealthBar health={data.health} />
			{/if}
			<div class="kpi-chart-area">
				<KpiGrid {kpis} thresholds={data.config?.kpi_thresholds ?? {}} />
				<PollRuntimeChart history={data.pollHistory ?? []} />
			</div>
			<AuditPreview events={data.audit?.events ?? []} />
		</div>
	</div>
</section>

<style>
	.dashboard {
		height: 100%;
		display: grid;
		grid-template-rows: auto 1fr;
		gap: var(--space-4);
		overflow: hidden;
		min-height: 0;
	}

	.dashboard h1 {
		margin: 0;
		font-size: var(--text-2xl);
		font-weight: var(--text-2xl-weight);
		line-height: var(--text-2xl-line-height);
		color: var(--text-primary);
	}

	.dashboard-layout {
		display: grid;
		grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
		gap: var(--space-4);
		min-height: 0;
		overflow: hidden;
	}

	.dashboard-main {
		display: grid;
		grid-template-rows: auto auto minmax(0, 1fr);
		gap: var(--space-4);
		min-height: 0;
		overflow: hidden;
	}

	@media (max-width: 900px) {
		.dashboard-layout {
			grid-template-columns: 1fr;
		}
	}

	.kpi-chart-area {
		display: grid;
		grid-template-columns: 1fr minmax(0, 320px);
		align-items: stretch;
		gap: var(--space-4);
		min-height: 0;
	}
</style>
