<script lang="ts">
	import ItemMetaPanel from '$lib/components/staging/ItemMetaPanel.svelte';
	import PhotoWheel from '$lib/components/staging/PhotoWheel.svelte';
	import TriageControls from '$lib/components/staging/TriageControls.svelte';
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

	let items = $derived($stagingQueue.items ?? []);
	let activeIndex = $derived($stagingQueue.activeIndex ?? 0);
	let selected = $derived<StagingItem | null>(items.length > 0 ? items[activeIndex] : null);
	let actionsDisabled = $derived(items.length === 0 || $stagingQueue.loading);

	async function runTriage(action: 'accept' | 'reject' | 'defer') {
		if (!selected) {
			return;
		}
		await stagingQueue.triageItem(action, selected.sha256);
	}

	function onKeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowLeft') {
			event.preventDefault();
			stagingQueue.shiftActive(-1);
			return;
		}

		if (event.key === 'ArrowRight') {
			event.preventDefault();
			stagingQueue.shiftActive(1);
			return;
		}

		if (event.key.toLowerCase() === 'a') {
			event.preventDefault();
			runTriage('accept');
			return;
		}

		if (event.key.toLowerCase() === 'r') {
			event.preventDefault();
			runTriage('reject');
			return;
		}

		if (event.key.toLowerCase() === 'd') {
			event.preventDefault();
			runTriage('defer');
		}
	}
</script>

<svelte:window on:keydown={onKeydown} />

<section class="staging-page" data-testid="staging-page">
	<h1>Staging Queue</h1>
	<PhotoWheel {items} {activeIndex} onSelect={(index) => stagingQueue.setActiveIndex(index)} />
	<TriageControls
		disabled={actionsDisabled}
		onAccept={() => runTriage('accept')}
		onReject={() => runTriage('reject')}
	/>
	<ItemMetaPanel item={selected} />
</section>

<style>
	.staging-page {
		display: grid;
		gap: var(--space-4);
	}
</style>
