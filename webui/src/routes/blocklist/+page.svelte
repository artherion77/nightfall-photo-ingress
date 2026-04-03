<script lang="ts">
	import BlockRuleList from '$lib/components/blocklist/BlockRuleList.svelte';

	let { data } = $props();
</script>

<section class="blocklist-page" data-testid="blocklist-page">
	<h1>Blocklist</h1>
	<BlockRuleList rules={data.blocklist?.rules ?? []} />
</section>

<style>
	.blocklist-page {
		display: grid;
		gap: var(--space-4);
	}
</style>
