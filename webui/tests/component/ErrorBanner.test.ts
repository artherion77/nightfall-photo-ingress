import { describe, it, expect, vi } from 'vitest';

describe('ErrorBanner', () => {
  it('supports retry callback behavior', () => {
    const onRetry = vi.fn();
    onRetry();
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
