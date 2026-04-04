<script lang="ts">
  interface RuleDraft {
    pattern: string;
    rule_type: 'filename' | 'regex';
    reason?: string | null;
    enabled?: boolean;
  }

  interface Props {
    mode?: 'create' | 'edit';
    initial?: RuleDraft | null;
    onSubmit?: (payload: RuleDraft) => void;
    onCancel?: () => void;
  }

  let { mode = 'create', initial = null, onSubmit, onCancel }: Props = $props();

  let pattern = $state('');
  let ruleType = $state<'filename' | 'regex'>('filename');
  let reason = $state('');
  let enabled = $state(true);

  $effect(() => {
    pattern = initial?.pattern ?? '';
    ruleType = initial?.rule_type ?? 'filename';
    reason = initial?.reason ?? '';
    enabled = initial?.enabled ?? true;
  });

  function submitForm(event: SubmitEvent) {
    event.preventDefault();
    const trimmed = pattern.trim();
    if (!trimmed) {
      return;
    }
    onSubmit?.({
      pattern: trimmed,
      rule_type: ruleType,
      reason: reason.trim() || null,
      enabled
    });
  }
</script>

<form class="block-rule-form" onsubmit={submitForm} data-testid="block-rule-form">
  <h3>{mode === 'create' ? 'Add Block Rule' : 'Edit Block Rule'}</h3>

  <label>
    Pattern
    <input bind:value={pattern} required placeholder="*.tmp" />
  </label>

  <label>
    Type
    <select bind:value={ruleType}>
      <option value="filename">filename</option>
      <option value="regex">regex</option>
    </select>
  </label>

  <label>
    Reason
    <input bind:value={reason} placeholder="Optional reason" />
  </label>

  <label class="enabled">
    <input type="checkbox" bind:checked={enabled} /> Enabled
  </label>

  <div class="actions">
    <button type="submit">{mode === 'create' ? 'Add Rule' : 'Save Rule'}</button>
    {#if mode === 'edit'}
      <button type="button" onclick={() => onCancel?.()}>Cancel Edit</button>
    {/if}
  </div>
</form>

<style>
  .block-rule-form {
    display: grid;
    gap: var(--space-3);
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  label {
    display: grid;
    gap: var(--space-1);
    font-size: var(--text-sm);
  }

  input,
  select {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--surface-hover);
    color: var(--text-primary);
    padding: var(--space-2);
  }

  .enabled {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .actions {
    display: flex;
    gap: var(--space-2);
  }

  button {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--surface-hover);
    color: var(--text-primary);
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
  }
</style>
