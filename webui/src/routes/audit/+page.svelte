<script lang="ts">
	import AuditTimeline from '$lib/components/audit/AuditTimeline.svelte';
	import { getAuditLog } from '$lib/api/audit';
        import type { AuditEvent as ApiAuditEvent, AuditPage } from '$lib/api/audit';

        interface PageData {
                audit?: AuditPage;
        }

        let { data }: { data: PageData } = $props();

		let events = $state<ApiAuditEvent[]>([]);
        let cursor = $state<string | null>(null);
        let hasMore = $state(false);
        let loading = $state(false);
        let filter = $state<string | null>(null);

	$effect(() => {
		events = data.audit?.events ?? [];
		cursor = data.audit?.cursor ?? null;
		hasMore = Boolean(data.audit?.has_more);
	});

	async function loadMore() {
		if (!hasMore || loading) {
			return;
		}
		loading = true;
		try {
			const page = await getAuditLog(cursor, 50, filter);
			events = [...events, ...(page.events ?? [])];
			cursor = page.cursor ?? null;
			hasMore = Boolean(page.has_more);
		} finally {
			loading = false;
		}
	}

	async function applyFilter(action: string | null) {
		loading = true;
		try {
			filter = action;
			const page = await getAuditLog(null, 50, action);
			events = page.events ?? [];
			cursor = page.cursor ?? null;
			hasMore = Boolean(page.has_more);
		} finally {
			loading = false;
		}
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
	<AuditTimeline {events} {loading} {hasMore} onLoadMore={loadMore} />
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
</style>
