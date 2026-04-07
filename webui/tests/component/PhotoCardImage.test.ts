import { describe, expect, it } from 'vitest';

import {
  fallbackLabel,
  imageErrorState,
  imageLoadedState,
  shouldShowFallback,
  shouldShowImage,
  shouldShowSkeleton,
  thumbnailSrc,
} from '$lib/components/staging/photocard-image';

describe('PhotoCard image contract', () => {
  it('uses thumbnail endpoint src format', () => {
    expect(thumbnailSrc('abc123')).toBe('/api/v1/thumbnails/abc123');
  });

  it('has deterministic loading and fallback visibility states', () => {
    expect(shouldShowSkeleton('loading')).toBe(true);
    expect(shouldShowImage('loaded')).toBe(true);
    expect(shouldShowFallback('error')).toBe(true);
  });

  it('maps fallback label by file extension', () => {
    expect(fallbackLabel('photo.jpg')).toBe('IMAGE ERROR');
    expect(fallbackLabel('clip.mp4')).toBe('VIDEO FILE');
    expect(fallbackLabel('doc.pdf')).toBe('DOCUMENT FILE');
  });

  it('exposes explicit state transitions', () => {
    expect(imageLoadedState()).toBe('loaded');
    expect(imageErrorState()).toBe('error');
  });
});
