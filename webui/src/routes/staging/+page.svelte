<script lang="ts">
	import ItemMetaPanel from '$lib/components/staging/ItemMetaPanel.svelte';
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

	let items = $derived($stagingQueue.items ?? []);
	let activeIndex = $derived($stagingQueue.activeIndex ?? 0);
	let selected = $derived<StagingItem | null>(items.length > 0 ? items[activeIndex] : null);
	let actionsDisabled = $derived(items.length === 0 || $stagingQueue.loading);

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
			onSelect={(index) => stagingQueue.setActiveIndex(index)}
			onAccept={() => runTriage('accept', generateIdempotencyKey())}
			onReject={() => runTriage('reject', generateIdempotencyKey())}
			onDefer={() => runTriage('defer', generateIdempotencyKey())}
		/>
		<div class="wheel-inline-controls">
			<TriageControls
				mode="inline"
				disabled={actionsDisabled}
				onAccept={(idempotencyKey) => runTriage('accept', idempotencyKey)}
				onReject={(idempotencyKey) => runTriage('reject', idempotencyKey)}
			/>
		</div>
	</div>
	<TriageControls
		mode="cta"
		disabled={actionsDisabled}
		onAccept={(idempotencyKey) => runTriage('accept', idempotencyKey)}
		onReject={(idempotencyKey) => runTriage('reject', idempotencyKey)}
	/>
	<ItemMetaPanel item={selected} />
</section>

<style>
	.staging-page {
		display: grid;
		gap: var(--space-4);
	}

	.wheel-shell {
		position: relative;
	}

	.wheel-inline-controls {
		position: absolute;
		right: 14%;
		top: 50%;
		transform: translateY(-50%);
		z-index: 20;
	}

	@media (max-width: 980px) {
		.wheel-inline-controls {
			position: static;
			transform: none;
			display: flex;
			justify-content: center;
			margin-top: calc(var(--space-4) * -1);
		}
	}
</style>
