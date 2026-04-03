<script lang="ts">
	import ConfigTable from '$lib/components/settings/ConfigTable.svelte';

	let { data } = $props();
</script>

<section class="settings-page" data-testid="settings-page">
	<h1>Settings</h1>
	<ConfigTable config={data.config ?? {}} />
</section>

<style>
	.settings-page {
		display: grid;
		gap: var(--space-4);
	}
</style>
