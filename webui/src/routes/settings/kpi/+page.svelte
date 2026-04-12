<script>
  import { onMount } from 'svelte';
  import { kpiThresholds } from '$lib/stores/kpiThresholds.svelte.js';

  let pendingWarning = 100;
  let pendingError = 500;
  let diskWarningPercent = 80;
  let diskErrorPercent = 95;

  let formState = {
    isDirty: false,
    validationErrors: {},
  };

  onMount(() => {
    kpiThresholds.load();
  });

  $: if ($kpiThresholds.thresholds) {
    pendingWarning = $kpiThresholds.thresholds.pending_warning;
    pendingError = $kpiThresholds.thresholds.pending_error;
    diskWarningPercent = $kpiThresholds.thresholds.disk_warning_percent;
    diskErrorPercent = $kpiThresholds.thresholds.disk_error_percent;
  }

  function validateForm() {
    const errors = {};

    if (pendingError <= pendingWarning) {
      errors.pending_error = 'Error threshold must be greater than warning threshold';
    }
    if (diskErrorPercent <= diskWarningPercent) {
      errors.disk_error_percent = 'Error threshold must be greater than warning threshold';
    }
    if (pendingWarning < 1 || pendingWarning > 9999) {
      errors.pending_warning = 'Value must be between 1 and 9999';
    }
    if (pendingError < 1 || pendingError > 9999) {
      errors.pending_error = 'Value must be between 1 and 9999';
    }
    if (diskWarningPercent < 1 || diskWarningPercent > 99) {
      errors.disk_warning_percent = 'Value must be between 1 and 99';
    }
    if (diskErrorPercent < 1 || diskErrorPercent > 99) {
      errors.disk_error_percent = 'Value must be between 1 and 99';
    }

    formState.validationErrors = errors;
    return Object.keys(errors).length === 0;
  }

  function handleChange() {
    formState.isDirty = true;
    formState.validationErrors = {};
  }

  async function handleSave() {
    if (!validateForm()) {
      return;
    }

    await kpiThresholds.update({
      pending_warning: pendingWarning,
      pending_error: pendingError,
      disk_warning_percent: diskWarningPercent,
      disk_error_percent: diskErrorPercent,
    });

    formState.isDirty = false;
  }

  async function handleReset() {
    if (confirm('Reset KPI thresholds to factory defaults?')) {
      await kpiThresholds.reset();
      formState.isDirty = false;
    }
  }

  function handleCancel() {
    // Reload from store to discard changes
    if ($kpiThresholds.thresholds) {
      pendingWarning = $kpiThresholds.thresholds.pending_warning;
      pendingError = $kpiThresholds.thresholds.pending_error;
      diskWarningPercent = $kpiThresholds.thresholds.disk_warning_percent;
      diskErrorPercent = $kpiThresholds.thresholds.disk_error_percent;
    }
    formState.isDirty = false;
    kpiThresholds.clearError();
  }
</script>

<div class="kpi-settings-page">
  <h1>KPI Thresholds</h1>
  <p class="subtitle">Configure warning and error thresholds for system metrics.</p>

  {#if $kpiThresholds.loading}
    <div class="loading">Loading KPI thresholds...</div>
  {:else}
    <form on:submit|preventDefault={handleSave}>
      <div class="form-section">
        <h2>Pending Queue Thresholds</h2>
        
        <div class="form-group">
          <label for="pending-warning">
            Warning Threshold (items)
            <span class="hint">Alert when queue reaches this count</span>
          </label>
          <input
            id="pending-warning"
            type="number"
            min="1"
            max="9999"
            bind:value={pendingWarning}
            on:change={handleChange}
            disabled={$kpiThresholds.saving}
          />
          {#if formState.validationErrors.pending_warning}
            <span class="error-message">{formState.validationErrors.pending_warning}</span>
          {/if}
        </div>

        <div class="form-group">
          <label for="pending-error">
            Error Threshold (items)
            <span class="hint">Trigger an error when queue reaches this count</span>
          </label>
          <input
            id="pending-error"
            type="number"
            min="1"
            max="9999"
            bind:value={pendingError}
            on:change={handleChange}
            disabled={$kpiThresholds.saving}
          />
          {#if formState.validationErrors.pending_error}
            <span class="error-message">{formState.validationErrors.pending_error}</span>
          {/if}
        </div>
      </div>

      <div class="form-section">
        <h2>Disk Usage Thresholds</h2>

        <div class="form-group">
          <label for="disk-warning">
            Warning Threshold (%)
            <span class="hint">Alert when disk usage exceeds this percentage</span>
          </label>
          <input
            id="disk-warning"
            type="number"
            min="1"
            max="99"
            bind:value={diskWarningPercent}
            on:change={handleChange}
            disabled={$kpiThresholds.saving}
          />
          {#if formState.validationErrors.disk_warning_percent}
            <span class="error-message">{formState.validationErrors.disk_warning_percent}</span>
          {/if}
        </div>

        <div class="form-group">
          <label for="disk-error">
            Error Threshold (%)
            <span class="hint">Trigger an error when disk usage exceeds this percentage</span>
          </label>
          <input
            id="disk-error"
            type="number"
            min="1"
            max="99"
            bind:value={diskErrorPercent}
            on:change={handleChange}
            disabled={$kpiThresholds.saving}
          />
          {#if formState.validationErrors.disk_error_percent}
            <span class="error-message">{formState.validationErrors.disk_error_percent}</span>
          {/if}
        </div>
      </div>

      {#if $kpiThresholds.error}
        <div class="error-banner">
          <strong>Error:</strong> {$kpiThresholds.error}
        </div>
      {/if}

      {#if $kpiThresholds.success}
        <div class="success-banner">
          ✓ KPI thresholds updated successfully
          {#if $kpiThresholds.updated_at}
            <span class="timestamp">at {new Date($kpiThresholds.updated_at).toLocaleString()}</span>
          {/if}
        </div>
      {/if}

      <div class="form-actions">
        <button
          type="submit"
          disabled={$kpiThresholds.saving || Object.keys(formState.validationErrors).length > 0}
          class="btn-primary"
        >
          {$kpiThresholds.saving ? 'Saving...' : 'Save Changes'}
        </button>

        <button
          type="button"
          on:click={handleCancel}
          disabled={$kpiThresholds.saving}
          class="btn-secondary"
        >
          Cancel
        </button>

        <button
          type="button"
          on:click={handleReset}
          disabled={$kpiThresholds.saving}
          class="btn-tertiary"
        >
          Reset to Defaults
        </button>
      </div>
    </form>
  {/if}
</div>

<style>
  .kpi-settings-page {
    max-width: 600px;
    margin: 0 auto;
    padding: 2rem;
  }

  h1 {
    font-size: 1.75rem;
    font-weight: 600;
    margin: 0 0 0.5rem 0;
  }

  .subtitle {
    color: var(--color-text-secondary, #666);
    margin: 0 0 2rem 0;
  }

  .loading {
    padding: 2rem;
    text-align: center;
    color: var(--color-text-secondary, #666);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }

  .form-section {
    padding: 1.5rem;
    border: 1px solid var(--color-border, #e0e0e0);
    border-radius: 4px;
    background-color: var(--color-background-secondary, #fafafa);
  }

  .form-section h2 {
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 1rem 0;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--color-border, #e0e0e0);
  }

  .form-group {
    margin-bottom: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .form-group:last-child {
    margin-bottom: 0;
  }

  label {
    font-weight: 500;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .hint {
    font-size: 0.875rem;
    font-weight: 400;
    color: var(--color-text-secondary, #666);
  }

  input {
    padding: 0.625rem 0.75rem;
    border: 1px solid var(--color-border, #d0d0d0);
    border-radius: 3px;
    font-size: 1rem;
    font-family: inherit;
  }

  input:focus {
    outline: none;
    border-color: var(--color-primary, #0066cc);
    box-shadow: 0 0 0 2px var(--color-primary-light, #e6f0ff);
  }

  input:disabled {
    background-color: var(--color-background-disabled, #f5f5f5);
    color: var(--color-text-disabled, #999);
    cursor: not-allowed;
  }

  .error-message {
    font-size: 0.875rem;
    color: var(--color-error, #d32f2f);
    margin-top: 0.25rem;
  }

  .error-banner,
  .success-banner {
    padding: 1rem;
    border-radius: 4px;
    margin: 1rem 0;
  }

  .error-banner {
    background-color: var(--color-error-background, #ffebee);
    color: var(--color-error, #d32f2f);
    border: 1px solid var(--color-error-border, #ffcdd2);
  }

  .success-banner {
    background-color: var(--color-success-background, #e8f5e9);
    color: var(--color-success, #388e3c);
    border: 1px solid var(--color-success-border, #c8e6c9);
  }

  .timestamp {
    font-size: 0.875rem;
    opacity: 0.8;
  }

  .form-actions {
    display: flex;
    gap: 1rem;
    padding-top: 1rem;
    border-top: 1px solid var(--color-border, #e0e0e0);
  }

  button {
    padding: 0.625rem 1rem;
    border: 1px solid transparent;
    border-radius: 3px;
    font-size: 1rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .btn-primary {
    background-color: var(--color-primary, #0066cc);
    color: white;
  }

  .btn-primary:hover:not(:disabled) {
    background-color: var(--color-primary-dark, #0052a3);
  }

  .btn-primary:disabled {
    background-color: var(--color-background-disabled, #f5f5f5);
    color: var(--color-text-disabled, #999);
    cursor: not-allowed;
  }

  .btn-secondary,
  .btn-tertiary {
    background-color: var(--color-background-secondary, #f5f5f5);
    color: var(--color-text, #333);
    border-color: var(--color-border, #d0d0d0);
  }

  .btn-secondary:hover:not(:disabled),
  .btn-tertiary:hover:not(:disabled) {
    background-color: var(--color-background-tertiary, #e0e0e0);
  }

  .btn-secondary:disabled,
  .btn-tertiary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
