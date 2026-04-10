import { describe, expect, it } from 'vitest';

import {
  fallbackLabel,
  imageErrorState,
  imageLoadedState,
  isImageFilename,
  isVideoFilename,
  shouldShowFallback,
  shouldShowImage,
  shouldShowSkeleton,
  thumbnailSrc,
} from '$lib/components/staging/photocard-image';

describe('PhotoCard image logic', () => {
  it('builds thumbnail API src from sha256', () => {
    expect(thumbnailSrc('abc123')).toBe('/api/v1/thumbnails/abc123?token=inspect-chunk3-token');
  });

  it('detects image and video filenames', () => {
    expect(isImageFilename('photo.JPG')).toBe(true);
    expect(isImageFilename('clip.mp4')).toBe(false);
    expect(isVideoFilename('clip.mp4')).toBe(true);
    expect(isVideoFilename('doc.pdf')).toBe(false);
  });

  it('maps fallback labels by file type', () => {
    expect(fallbackLabel('frame.jpg')).toBe('IMAGE ERROR');
    expect(fallbackLabel('movie.mov')).toBe('VIDEO FILE');
    expect(fallbackLabel('CLIP.MOV')).toBe('VIDEO FILE');
    expect(fallbackLabel('notes.pdf')).toBe('DOCUMENT FILE');
    expect(fallbackLabel('archive.bin')).toBe('DOCUMENT FILE');
  });

  it('exposes deterministic state transitions for load and error', () => {
    expect(imageLoadedState()).toBe('loaded');
    expect(imageErrorState()).toBe('error');
  });

  it('enforces skeleton, image, and fallback visibility contract by state', () => {
    expect(shouldShowSkeleton('loading')).toBe(true);
    expect(shouldShowSkeleton('loaded')).toBe(false);

    expect(shouldShowImage('loaded')).toBe(true);
    expect(shouldShowImage('error')).toBe(false);

    expect(shouldShowFallback('error')).toBe(true);
    expect(shouldShowFallback('loading')).toBe(false);
  });
});
