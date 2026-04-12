<script lang="ts">
	import AuditPreview from '$lib/components/dashboard/AuditPreview.svelte';
	import FilterSidebar from '$lib/components/dashboard/FilterSidebar.svelte';
	import HealthBar from '$lib/components/dashboard/HealthBar.svelte';
	import KpiGrid from '$lib/components/dashboard/KpiGrid.svelte';
	import PollRuntimeChart from '$lib/components/dashboard/PollRuntimeChart.svelte';
	import {
		applyDashboardFileTypeFilters,
		createFilterStore,
		deriveDashboardFileTypeOptions,
	} from '$lib/stores/filterStore';
	import type { AuditDailySummary, AuditPage } from '$lib/api/audit';
        import type { StagingPage } from '$lib/api/staging';
        import type { HealthResponse } from '$lib/api/health';
        import type { EffectiveConfig } from '$lib/api/config';

        interface PageData {
                staging?: StagingPage;
                audit?: AuditPage;
			auditSummary?: AuditDailySummary;
                config?: EffectiveConfig;
                health?: HealthResponse;
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
	const filteredItems = $derived(applyDashboardFileTypeFilters(dashboardItems, $dashboardFilterStore));

	function formatItemType(filename: string): string {
		const normalized = filename.toLowerCase().trim();
		const dot = normalized.lastIndexOf('.');
		if (dot <= 0 || dot === normalized.length - 1) {
			return 'UNKNOWN';
		}
		return normalized.slice(dot + 1).toUpperCase();
	}
</script>

<section class="dashboard" data-testid="dashboard-page">
	<h1>Photo-Ingress Dashboard</h1>
	<div class="dashboard-layout">
		<FilterSidebar
			options={filterOptions}
			activeFilters={$dashboardFilterStore}
			onToggle={(id) => dashboardFilterStore.toggle(id)}
			onClear={() => dashboardFilterStore.clear()}
		/>

		<div class="dashboard-main">
			<KpiGrid {kpis} thresholds={data.config?.kpi_thresholds ?? {}} />
			{#if data.health}
			<HealthBar health={data.health} />
			{/if}
			<PollRuntimeChart values={[kpis.last_poll_duration_s]} />

			<section class="dashboard-files" data-testid="dashboard-file-list">
				<div class="files-header">
					<h2>Pending Files</h2>
					<p data-testid="dashboard-file-count">{filteredItems.length} of {dashboardItems.length}</p>
				</div>
				{#if filteredItems.length === 0}
					<p class="files-empty" data-testid="dashboard-file-list-empty">No files match the selected filters.</p>
				{:else}
					<ul>
						{#each filteredItems as item}
							<li data-testid="dashboard-file-list-item">
								<div class="file-main">
									<span class="file-name" title={item.filename}>{item.filename}</span>
									<span class="file-type" data-testid="dashboard-file-type-pill">{formatItemType(item.filename)}</span>
								</div>
								<span class="file-id">{item.sha256.slice(0, 12)}...</span>
							</li>
						{/each}
					</ul>
				{/if}
			</section>

			<AuditPreview events={data.audit?.events ?? []} />
		</div>
	</div>
</section>

<style>
	.dashboard {
		display: grid;
		gap: var(--space-4);
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
	}

	.dashboard-main {
		display: grid;
		gap: var(--space-4);
	}

	.dashboard-files {
		padding: var(--space-4);
		border: 1px solid var(--border-default);
		border-radius: var(--radius-md);
		background: var(--surface-card);
	}

	.files-header {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--space-3);
		margin-bottom: var(--space-3);
	}

	.files-header h2 {
		margin: 0;
		font-size: var(--text-md);
		font-weight: var(--text-md-weight);
		line-height: var(--text-md-line-height);
	}

	.files-header p {
		margin: 0;
		color: var(--text-muted);
		font-size: var(--text-sm);
	}

	.dashboard-files ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: var(--space-2);
		max-height: var(--space-8);
		overflow-y: auto;
		padding-right: var(--space-1);
	}

	.dashboard-files li {
		display: flex;
		justify-content: space-between;
		gap: var(--space-3);
		padding: var(--space-2) var(--space-3);
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: var(--surface-raised);
	}

	.file-main {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		min-width: 0;
	}

	.file-name {
		color: var(--text-primary);
		font-size: var(--text-sm);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 360px;
	}

	.file-type {
		display: inline-flex;
		align-items: center;
		height: 20px;
		padding: 0 var(--space-2);
		border-radius: var(--radius-full);
		border: 1px solid var(--border-default);
		font-size: var(--text-xs);
		color: var(--text-secondary);
	}

	.file-id {
		font-family: var(--font-family-mono);
		font-size: var(--text-mono-sm);
		color: var(--text-muted);
		white-space: nowrap;
	}

	.files-empty {
		margin: 0;
		font-size: var(--text-sm);
		color: var(--text-muted);
	}

	@media (max-width: 900px) {
		.dashboard-layout {
			grid-template-columns: 1fr;
		}
	}
</style>
