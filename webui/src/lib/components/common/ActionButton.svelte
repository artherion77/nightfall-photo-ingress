<script lang="ts">
  interface Props {
    variant?: 'primary' | 'accept' | 'reject' | 'defer' | 'destructive';
    label: string;
    disabled?: boolean;
    onclick?: () => void;
  }

  let { variant = 'primary', label, disabled = false, onclick }: Props = $props();

  const variantClasses = {
    primary: 'btn-primary',
    accept: 'btn-accept',
    reject: 'btn-reject',
    defer: 'btn-defer',
    destructive: 'btn-destructive'
  };
</script>

<button
  class="action-button {variantClasses[variant]}"
  {disabled}
  {onclick}
>
  {label}
</button>

<style>
  .action-button {
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-md);
    border: none;
    font-size: var(--text-base);
    font-weight: var(--text-md-weight);
    cursor: pointer;
    transition: all var(--duration-default) var(--easing-default);
    font-family: var(--font-family-base);
  }

  .action-button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background-color: var(--action-primary);
    color: var(--color-bg-900);
  }

  .btn-primary:hover:not(:disabled) {
    background-color: var(--action-primary-hover);
  }

  .btn-accept {
    background-color: var(--action-accept);
    color: var(--color-bg-900);
  }

  .btn-accept:hover:not(:disabled) {
    background-color: #10e8cc;
  }

  .btn-reject {
    background-color: var(--action-reject);
    color: white;
  }

  .btn-reject:hover:not(:disabled) {
    background-color: #f67575;
  }

  .btn-defer {
    background-color: var(--action-primary);
    color: var(--color-bg-900);
  }

  .btn-defer:hover:not(:disabled) {
    background-color: var(--action-primary-hover);
  }

  .btn-destructive {
    background-color: var(--action-destructive);
    color: white;
  }

  .btn-destructive:hover:not(:disabled) {
    background-color: #f67575;
  }
</style>
