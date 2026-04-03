<script lang="ts">
	import ItemMetaPanel from '$lib/components/staging/ItemMetaPanel.svelte';
	import PhotoWheel from '$lib/components/staging/PhotoWheel.svelte';

	let { data } = $props();

	let items = $derived(data.staging?.items ?? []);
	let selected = $derived(items.length > 0 ? items[0] : null);
</script>

<section class="staging-page" data-testid="staging-page">
	<h1>Staging Queue</h1>
	<PhotoWheel {items} activeIndex={0} />
	<ItemMetaPanel item={selected} />
</section>

<style>
	.staging-page {
		display: grid;
		gap: var(--space-4);
	}
</style>
