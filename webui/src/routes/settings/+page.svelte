<script lang="ts">
	import ConfigTable from '$lib/components/settings/ConfigTable.svelte';
	import type { EffectiveConfig } from '$lib/api/config';

	interface PageData {
		config?: EffectiveConfig;
	}

	let { data }: { data: PageData } = $props();
</script>

<section class="settings-page" data-testid="settings-page">
	<h1>Settings</h1>
	<ConfigTable config={(data.config ?? {}) as Record<string, unknown>} />
</section>

<style>
	.settings-page {
		display: grid;
		gap: var(--space-4);
	}
</style>
