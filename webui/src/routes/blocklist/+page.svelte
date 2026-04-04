<script lang="ts">
	import BlockRuleList from '$lib/components/blocklist/BlockRuleList.svelte';
	import BlockRuleForm from '$lib/components/blocklist/BlockRuleForm.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import { blocklist } from '$lib/stores/blocklist.svelte';

	type BlockRule = {
		id: number;
		pattern: string;
		rule_type: 'filename' | 'regex';
		reason?: string | null;
		enabled: boolean;
	};

	let { data }: { data: { blocklist?: { rules?: BlockRule[] } } } = $props();
	let editingRule = $state<BlockRule | null>(null);
	let deletingRule = $state<BlockRule | null>(null);

	$effect(() => {
		blocklist.hydrate(data.blocklist?.rules ?? []);
	});

	async function handleCreate(payload: { pattern: string; rule_type: 'filename' | 'regex'; reason?: string | null; enabled?: boolean }) {
		await blocklist.createRule(payload);
	}

	async function handleEditSubmit(payload: { pattern: string; rule_type: 'filename' | 'regex'; reason?: string | null; enabled?: boolean }) {
		if (!editingRule) {
			return;
		}
		await blocklist.updateRule(editingRule.id, payload);
		editingRule = null;
	}

	async function handleToggle(rule: BlockRule) {
		await blocklist.updateRule(rule.id, { enabled: !rule.enabled });
	}

	async function confirmDelete() {
		if (!deletingRule) {
			return;
		}
		await blocklist.deleteRule(deletingRule.id);
		deletingRule = null;
	}
</script>

<section class="blocklist-page" data-testid="blocklist-page">
	<h1>Blocklist</h1>

	<BlockRuleForm mode="create" onSubmit={handleCreate} />

	{#if editingRule}
		<BlockRuleForm
			mode="edit"
			initial={editingRule}
			onSubmit={handleEditSubmit}
			onCancel={() => {
				editingRule = null;
			}}
		/>
	{/if}

	<BlockRuleList
		rules={$blocklist.rules ?? []}
		onToggle={handleToggle}
		onEdit={(rule) => {
			editingRule = rule;
		}}
		onDelete={(rule) => {
			deletingRule = rule;
		}}
	/>

	<ConfirmDialog
		open={deletingRule !== null}
		title="Delete Block Rule"
		message={deletingRule ? `Delete rule '${deletingRule.pattern}'?` : ''}
		onConfirm={confirmDelete}
		onCancel={() => {
			deletingRule = null;
		}}
	/>
</section>

<style>
	.blocklist-page {
		display: grid;
		gap: var(--space-4);
	}
</style>
