<script lang="ts">
	import AuditTimeline from '$lib/components/audit/AuditTimeline.svelte';
	import { onDestroy } from 'svelte';
	import type { AuditPage } from '$lib/api/audit';
	import { auditTimelinePaging } from '$lib/stores/auditTimelinePaging.svelte';

        interface PageData {
                audit?: AuditPage;
        }

        let { data }: { data: PageData } = $props();
	let timelineState = $state<any>({
		currentPage: 0,
		entries: [],
		loading: false,
		terminal: false,
		error: null,
	});
	let filter = $state<string | null>(null);

	const unsubscribe = auditTimelinePaging.subscribe((value) => {
		timelineState = value;
	});

	$effect(() => {
		auditTimelinePaging.initialize(data.audit ?? { events: [], cursor: null, has_more: false }, filter);
	});

	onDestroy(() => {
		unsubscribe();
		auditTimelinePaging.reset();
	});

	async function loadMore() {
		await auditTimelinePaging.loadNext();
	}

	async function applyFilter(action: string | null) {
		filter = action;
		await auditTimelinePaging.setFilter(action);
	}
</script>

<section class="audit-page" data-testid="audit-page">
	<h1>Audit Timeline</h1>
	<div class="filters">
		<button onclick={() => applyFilter(null)}>All</button>
		<button onclick={() => applyFilter('triage_accept_applied')}>Accepted</button>
		<button onclick={() => applyFilter('triage_reject_applied')}>Rejected</button>
		<button onclick={() => applyFilter('triage_defer_applied')}>Deferred</button>
	</div>
	{#if timelineState.error}
		<p class="error" data-testid="audit-load-error">{timelineState.error}</p>
	{/if}
	<AuditTimeline
		events={timelineState.entries}
		loading={timelineState.loading}
		hasMore={!timelineState.terminal}
		onLoadMore={loadMore}
	/>
</section>

<style>
	.audit-page {
		display: grid;
		gap: var(--space-4);
	}

	.filters {
		display: flex;
		gap: var(--space-2);
	}

	.filters button {
		padding: var(--space-2) var(--space-3);
		border: 1px solid var(--border-default);
		background: var(--surface-card);
		color: var(--text-primary);
		border-radius: var(--radius-md);
		cursor: pointer;
	}

	.error {
		margin: 0;
		padding: var(--space-2) var(--space-3);
		border: 1px solid var(--status-error);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--status-error) 10%, var(--surface-card));
		color: var(--status-error);
		font-size: var(--text-sm);
	}
</style>
