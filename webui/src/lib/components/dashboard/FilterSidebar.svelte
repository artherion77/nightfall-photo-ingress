<script lang="ts">
  import type { DashboardAccountOption, DashboardFileTypeOption } from '$lib/stores/filterStore';

  interface Props {
    options: DashboardFileTypeOption[];
    accountOptions: DashboardAccountOption[];
    activeFilters: string[];
    activeAccounts: Set<string>;
    onToggle: (filterId: string) => void;
    onToggleAccount: (account: string) => void;
    onClear: () => void;
  }

  let { options, accountOptions, activeFilters, activeAccounts, onToggle, onToggleAccount, onClear }: Props = $props();

  const activeSet = $derived(new Set(activeFilters));
  const activeAccountsSet = $derived(activeAccounts);
</script>

<aside class="filter-sidebar" data-testid="dashboard-filter-sidebar" aria-label="Dashboard file type filters">
  <div class="header">
    <h2>Filters</h2>
    <button
      type="button"
      class="clear-button"
      onclick={onClear}
      disabled={activeFilters.length === 0 && activeAccounts.size === 0}
      data-testid="dashboard-filter-clear"
    >
      Clear
    </button>
  </div>

  {#if options.length === 0}
    <p class="empty">No file types available.</p>
  {:else}
    <ul class="filter-list">
      {#each options as option}
        <li>
          <button
            type="button"
            class:active={activeSet.has(option.id)}
            style={`--filter-accent: var(${option.tokenVar})`}
            onclick={() => onToggle(option.id)}
            data-testid={`dashboard-filter-option-${option.id}`}
          >
            <span class="swatch" aria-hidden="true"></span>
            <span class="label">{option.label}</span>
            <span class="count">{option.count}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  {#if accountOptions.length > 0}
    <div class="account-section" data-testid="dashboard-account-filter-section">
      <h3>Accounts</h3>
      <ul class="filter-list">
        {#each accountOptions as option}
          <li>
            <button
              type="button"
              class:active={activeAccountsSet.has(option.id)}
              style={`--filter-accent: var(${option.tokenVar})`}
              onclick={() => onToggleAccount(option.id)}
              data-testid={`dashboard-account-filter-option-${option.id}`}
            >
              <span class="swatch" aria-hidden="true"></span>
              <span class="label">{option.label}</span>
              <span class="count">{option.count}</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</aside>

<style>
  .filter-sidebar {
    background: var(--surface-card);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 220px;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-2);
  }

  h2 {
    margin: 0;
    font-size: var(--text-md);
    font-weight: var(--text-md-weight);
    line-height: var(--text-md-line-height);
    color: var(--text-primary);
  }

  h3 {
    margin: 0;
    font-size: var(--text-sm);
    font-weight: var(--text-md-weight);
    line-height: var(--text-sm-line-height);
    color: var(--text-secondary);
  }

  .account-section {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .clear-button {
    border: 1px solid var(--border-default);
    background: transparent;
    color: var(--text-secondary);
    border-radius: var(--radius-sm);
    padding: 0 var(--space-2);
    height: 28px;
    cursor: pointer;
  }

  .clear-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .filter-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .filter-list button {
    width: 100%;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    background: var(--surface-raised);
    color: var(--text-secondary);
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
    text-align: left;
  }

  .filter-list button.active {
    border-color: var(--filter-accent);
    color: var(--text-primary);
    box-shadow: inset 0 0 0 1px var(--filter-accent);
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: var(--radius-full);
    background: var(--filter-accent);
  }

  .label {
    font-size: var(--text-sm);
    font-weight: var(--text-sm-weight);
    line-height: var(--text-sm-line-height);
  }

  .count {
    font-family: var(--font-family-mono);
    font-size: var(--text-mono-sm);
    color: var(--text-muted);
  }

  .empty {
    margin: 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
  }

  @media (max-width: 900px) {
    .filter-sidebar {
      min-width: 0;
    }
  }
</style>
