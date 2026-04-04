<script lang="ts">
  import EmptyState from '$lib/components/common/EmptyState.svelte';

  interface Rule {
    id: number;
    pattern: string;
    rule_type: 'filename' | 'regex';
    enabled: boolean;
    reason?: string;
  }

  interface Props {
    rules: Rule[];
    onToggle?: (rule: Rule) => void;
    onEdit?: (rule: Rule) => void;
    onDelete?: (rule: Rule) => void;
  }

  let { rules, onToggle, onEdit, onDelete }: Props = $props();
</script>

<section class="rules" data-testid="block-rule-list">
  {#if rules.length === 0}
    <EmptyState message="No block rules configured." />
  {:else}
    <ul>
      {#each rules as rule}
        <li>
          <span class="pattern">{rule.pattern}</span>
          <span>{rule.rule_type}</span>
          <span class:enabled={rule.enabled} class:disabled={!rule.enabled}>
            {rule.enabled ? 'enabled' : 'disabled'}
          </span>
          <span>{rule.reason ?? ''}</span>
          <div class="actions">
            <button onclick={() => onToggle?.(rule)}>{rule.enabled ? 'Disable' : 'Enable'}</button>
            <button onclick={() => onEdit?.(rule)}>Edit</button>
            <button class="danger" onclick={() => onDelete?.(rule)}>Delete</button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .rules {
    padding: var(--space-4);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-card);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  li {
    display: grid;
    grid-template-columns: 2fr 100px 80px 2fr 220px;
    gap: var(--space-3);
    font-size: var(--text-sm);
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: var(--space-2);
  }

  .actions {
    display: flex;
    gap: var(--space-2);
    justify-content: flex-end;
  }

  .actions button {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--surface-hover);
    color: var(--text-primary);
    padding: 2px 8px;
    cursor: pointer;
    font-size: var(--text-sm);
  }

  .actions button.danger {
    border-color: var(--action-reject);
    color: var(--action-reject);
  }

  .enabled { color: var(--status-ok); }
  .disabled { color: var(--text-muted); }
  .pattern { font-family: var(--font-family-mono); }
</style>
