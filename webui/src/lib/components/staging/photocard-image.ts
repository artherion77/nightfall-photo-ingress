import { PUBLIC_API_TOKEN } from '$env/static/public';

export type ImageState = 'loading' | 'loaded' | 'error';

export function thumbnailSrc(sha256: string): string {
  return `/api/v1/thumbnails/${sha256}?token=${encodeURIComponent(PUBLIC_API_TOKEN)}`;
}

export function isImageFilename(filename: string): boolean {
  return /\.(jpg|jpeg|png|webp|gif|bmp|tiff|heic|heif)$/i.test(filename);
}

export function isVideoFilename(filename: string): boolean {
  return /\.(mp4|mov|m4v|avi|mkv|webm)$/i.test(filename);
}

export function fallbackLabel(filename: string): string {
  if (isImageFilename(filename)) return 'IMAGE ERROR';
  if (isVideoFilename(filename)) return 'VIDEO FILE';
  return 'DOCUMENT FILE';
}

export function imageLoadedState(): ImageState {
  return 'loaded';
}

export function imageErrorState(): ImageState {
  return 'error';
}

export function shouldShowSkeleton(state: ImageState): boolean {
  return state === 'loading';
}

export function shouldShowImage(state: ImageState): boolean {
  return state === 'loaded';
}

export function shouldShowFallback(state: ImageState): boolean {
  return state === 'error';
}