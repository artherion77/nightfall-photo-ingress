<script lang="ts">
	import DetailSheet from '$lib/components/staging/DetailSheet.svelte';
	import PhotoWheel from '$lib/components/staging/PhotoWheel.svelte';
	import TriageControls from '$lib/components/staging/TriageControls.svelte';
	import { generateIdempotencyKey } from '$lib/api/triage';
	import { stagingQueue } from '$lib/stores/stagingQueue.svelte';

	type StagingItem = {
		sha256: string;
		filename: string;
		size_bytes: number;
		first_seen_at?: string;
		updated_at?: string;
		account?: string;
		onedrive_id?: string;
	};

	type PageData = {
		staging?: {
			items?: StagingItem[];
		};
	};

	let { data }: { data: PageData } = $props();

	$effect(() => {
		stagingQueue.hydrate(data.staging?.items ?? []);
	});

	$effect(() => {
		const id = setInterval(() => {
			stagingQueue.loadPage();
		}, 30_000);
		return () => clearInterval(id);
	});

	let items = $derived($stagingQueue.items ?? []);
	let activeIndex = $derived($stagingQueue.activeIndex ?? 0);
	let selected = $derived<StagingItem | null>(items.length > 0 ? items[activeIndex] : null);
	let actionsDisabled = $derived(items.length === 0 || $stagingQueue.loading);
	let dragActive = $state(false);
	let detailSheetOpen = $state(false);

	async function runTriage(action: 'accept' | 'reject' | 'defer', idempotencyKey: string) {
		if (!selected) {
			return;
		}
		await stagingQueue.triageItem(action, selected.sha256, idempotencyKey);
	}
</script>

<section class="staging-page" data-testid="staging-page">
	<h1>Staging Queue</h1>
	<div class="wheel-shell">
		<PhotoWheel
			{items}
			{activeIndex}
			{actionsDisabled}
			onOpenDetails={() => {
				detailSheetOpen = true;
			}}
			onDragStateChange={(dragging) => {
				dragActive = dragging;
			}}
			onSelect={(index) => stagingQueue.setActiveIndex(index)}
			onAccept={() => runTriage('accept', generateIdempotencyKey())}
			onReject={() => runTriage('reject', generateIdempotencyKey())}
			onDefer={() => runTriage('defer', generateIdempotencyKey())}
		/>
	</div>
	<TriageControls
		mode="cta"
		dragActive={dragActive}
		disabled={actionsDisabled}
		onAccept={(idempotencyKey) => runTriage('accept', idempotencyKey)}
		onReject={(idempotencyKey) => runTriage('reject', idempotencyKey)}
	/>
	<DetailSheet
		open={detailSheetOpen}
		item={selected}
		onClose={() => {
			detailSheetOpen = false;
		}}
	/>
</section>

<style>
	.staging-page {
		height: 100%;
		display: grid;
		grid-template-rows: auto 1fr auto auto;
		gap: var(--space-4);
		overflow: hidden;
		min-height: 0;
	}

	.wheel-shell {
		position: relative;
		min-height: 0;
	}
</style>
