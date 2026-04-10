import { expect, test, type Page, type Response, type Route, type TestInfo } from '@playwright/test';

type StagingItem = {
  sha256: string;
  filename: string;
  account?: string;
  first_seen_at?: string;
};

type ThumbState = {
  signature: string;
  state: string;
  fallbackText: string | null;
  rect: { width: number; height: number };
  hasButton: boolean;
};

const SUCCESS_PNG_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WnM6xQAAAAASUVORK5CYII=';

function signatureForItem(item: StagingItem): string {
  return `${item.filename}|SHA-256: ${item.sha256.slice(0, 16)}...`;
}

function fallbackLabelForFilename(filename: string): string {
  if (/\.(jpg|jpeg|png|webp|gif|bmp|tiff|heic|heif)$/i.test(filename)) return 'IMAGE ERROR';
  if (/\.(mp4|mov|m4v|avi|mkv|webm)$/i.test(filename)) return 'VIDEO FILE';
  return 'DOCUMENT FILE';
}

function normalizeToPath(value: string): string {
  return new URL(value, 'http://staging.local').pathname;
}

async function waitForAuthenticatedStagingData(page: Page): Promise<StagingItem[]> {
  const responsePromise = page.waitForResponse(
    (response: Response) => response.url().includes('/api/v1/staging') && response.request().method() === 'GET',
  );
  await page.goto('/staging', { waitUntil: 'networkidle' });
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const payload = (await response.json()) as { items?: StagingItem[] };
  expect(Array.isArray(payload.items)).toBeTruthy();
  expect((payload.items ?? []).length).toBeGreaterThan(1);
  await page.waitForSelector('[data-testid="photo-wheel"] .slot.is-active');
  await page.waitForTimeout(280);
  return payload.items ?? [];
}

async function activeSignature(page: Page): Promise<string> {
  return page.locator('[data-testid="photo-wheel"] .slot.is-active').evaluate((node: Element) => {
    const title = node.querySelector('h3')?.textContent?.trim() ?? '';
    const shaLine = (Array.from(node.querySelectorAll('p')) as HTMLParagraphElement[])
      .map((p) => p.textContent?.trim() ?? '')
      .find((line) => line.startsWith('SHA-256:')) ?? '';
    return `${title}|${shaLine}`;
  });
}

async function pressStep(page: Page, direction: 1 | -1): Promise<void> {
  await page.keyboard.press(direction > 0 ? 'ArrowRight' : 'ArrowLeft');
  await page.waitForTimeout(220);
}

async function stepAndDetectChange(page: Page, direction: 1 | -1): Promise<boolean> {
  const before = await activeSignature(page);
  for (let i = 0; i < 4; i += 1) {
    await pressStep(page, direction);
    const after = await activeSignature(page);
    if (after !== before) {
      return true;
    }
  }
  return false;
}

async function stepUntilBoundary(page: Page, direction: 1 | -1): Promise<void> {
  let stableCount = 0;
  let last = await activeSignature(page);
  for (let i = 0; i < 80; i += 1) {
    await pressStep(page, direction);
    const next = await activeSignature(page);
    if (next === last) {
      stableCount += 1;
      if (stableCount >= 2) {
        return;
      }
    } else {
      stableCount = 0;
    }
    last = next;
  }
}

async function orderedSignatures(page: Page): Promise<string[]> {
  await stepUntilBoundary(page, -1);
  const signatures: string[] = [await activeSignature(page)];
  for (let i = 0; i < 220; i += 1) {
    const changed = await stepAndDetectChange(page, 1);
    if (!changed) {
      break;
    }
    signatures.push(await activeSignature(page));
  }
  await stepUntilBoundary(page, -1);
  return signatures;
}

async function gotoIndexBySignature(page: Page, ordered: string[], targetIndex: number): Promise<void> {
  const currentSig = await activeSignature(page);
  let currentIndex = ordered.indexOf(currentSig);
  if (currentIndex < 0) {
    throw new Error('active signature is not in ordered signature list');
  }

  for (let guard = 0; guard < 220 && currentIndex !== targetIndex; guard += 1) {
    const direction: 1 | -1 = targetIndex > currentIndex ? 1 : -1;
    const changed = await stepAndDetectChange(page, direction);
    if (!changed) {
      break;
    }
    currentIndex = ordered.indexOf(await activeSignature(page));
  }

  expect(currentIndex).toBe(targetIndex);
}

async function renderedSlots(page: Page): Promise<
  Array<{
    signature: string;
    active: boolean;
    imgSrc: string;
    state: string;
  }>
> {
  return page.evaluate(() => {
    const slots = Array.from(document.querySelectorAll('[data-testid="photo-wheel"] .slot')) as HTMLElement[];
    return slots.map((slot) => {
      const title = slot.querySelector('h3')?.textContent?.trim() ?? '';
      const shaLine = Array.from(slot.querySelectorAll('p'))
        .map((p) => p.textContent?.trim() ?? '')
        .find((line) => line.startsWith('SHA-256:')) ?? '';
      const thumb = slot.querySelector('[data-testid="photo-thumb"]') as HTMLElement | null;
      const img = slot.querySelector('img') as HTMLImageElement | null;
      return {
        signature: `${title}|${shaLine}`,
        active: slot.classList.contains('is-active'),
        imgSrc: img?.getAttribute('src') ?? '',
        state: thumb?.getAttribute('data-state') ?? 'unknown',
      };
    });
  });
}

async function renderedSignatures(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const slots = Array.from(document.querySelectorAll('[data-testid="photo-wheel"] .slot')) as HTMLElement[];
    return slots.map((slot) => {
      const title = slot.querySelector('h3')?.textContent?.trim() ?? '';
      const shaLine = Array.from(slot.querySelectorAll('p'))
        .map((p) => p.textContent?.trim() ?? '')
        .find((line) => line.startsWith('SHA-256:')) ?? '';
      return `${title}|${shaLine}`;
    });
  });
}

async function thumbStateForSignature(page: Page, signature: string): Promise<ThumbState | null> {
  return page.evaluate((targetSignature: string) => {
    const targetShaPrefix = (targetSignature.match(/SHA-256:\s*([a-f0-9]{16})\.\.\./i) ?? [])[1] ?? '';
    const slots = Array.from(document.querySelectorAll('[data-testid="photo-wheel"] .slot')) as HTMLElement[];
    for (const slot of slots) {
      const title = slot.querySelector('h3')?.textContent?.trim() ?? '';
      const shaLine = Array.from(slot.querySelectorAll('p'))
        .map((p) => p.textContent?.trim() ?? '')
        .find((line) => line.startsWith('SHA-256:')) ?? '';
      const signature = `${title}|${shaLine}`;
      const card = slot.querySelector('[data-testid="photo-card"]') as HTMLElement | null;
      const sha256 = card?.getAttribute('data-sha256') ?? '';
      const matchesByPrefix = Boolean(targetShaPrefix) && sha256.startsWith(targetShaPrefix);
      if (signature !== targetSignature && !matchesByPrefix) {
        continue;
      }
      const thumb = slot.querySelector('[data-testid="photo-thumb"]') as HTMLElement | null;
      const fallback = slot.querySelector('[data-testid="thumb-fallback"]') as HTMLElement | null;
      const fallbackButton = fallback?.querySelector('button') as HTMLButtonElement | null;
      return {
        signature,
        state: thumb?.getAttribute('data-state') ?? 'unknown',
        fallbackText: fallback?.textContent?.trim() ?? null,
        rect: {
          width: thumb?.offsetWidth ?? 0,
          height: thumb?.offsetHeight ?? 0,
        },
        hasButton: Boolean(fallbackButton),
      } satisfies ThumbState;
    }
    return null;
  }, signature);
}

test.describe('PhotoWheel — Thumbnail Behavior', () => {
  test('C1 render-window entry and idle preload behave on staging system data', async ({ page, browserName }: { page: Page; browserName: string }) => {
    test.skip(browserName !== 'chromium', 'suite targets Chromium only for deterministic network checks');

    await page.addInitScript(() => {
      const assignments: string[] = [];
      const OriginalImage = window.Image;
      class TrackingImage extends OriginalImage {
        override set src(value: string) {
          assignments.push(String(value));
          super.src = value;
        }
        override get src(): string {
          return super.src;
        }
      }
      Object.defineProperty(window, '__nightfallPreloadAssignments', {
        value: assignments,
        configurable: true,
      });
      window.Image = TrackingImage as typeof Image;
    });

    const items = await waitForAuthenticatedStagingData(page);
    test.skip(items.length < 11, 'need at least 11 staging items to validate activeIndex 10 windowing');

    const ordered = await orderedSignatures(page);
    await gotoIndexBySignature(page, ordered, 10);

    const slots = await renderedSlots(page);
    // Window size can vary by runtime viewport/layout transforms; enforce invariant bounds.
    expect(slots.length).toBeGreaterThanOrEqual(9);
    expect(slots.length).toBeLessThanOrEqual(11);
    expect(slots.filter((slot) => slot.active)).toHaveLength(1);
    expect(slots.every((slot) => normalizeToPath(slot.imgSrc).startsWith('/api/v1/thumbnails/'))).toBeTruthy();

    await page.waitForTimeout(450);

    const preloadAssignments = await page.evaluate(() => {
      return ((window as typeof window & { __nightfallPreloadAssignments?: string[] }).__nightfallPreloadAssignments ?? []).map(
        (value) => new URL(value, window.location.href).pathname,
      );
    });

    const activePosition = slots.findIndex((slot) => slot.active);
    const expectedPreloadPaths = slots
      .filter((_, index) => index !== activePosition && Math.abs(index - activePosition) <= 3)
      .map((slot) => normalizeToPath(slot.imgSrc));
    expect(preloadAssignments).toEqual(expect.arrayContaining(expectedPreloadPaths));

    const before = await activeSignature(page);
    await pressStep(page, 1);
    const after = await activeSignature(page);
    expect(after).not.toBe(before);
  });

  test('C2 C3 C5 fallback retry and UX invariants behave on staging system data', async ({ page }: { page: Page }, testInfo: TestInfo) => {
    test.skip(testInfo.project.name !== 'desktop-chromium', 'route-based retry validation runs once on desktop');

    const items = await waitForAuthenticatedStagingData(page);
    test.skip(items.length < 12, 'need at least 12 staging items to validate remount retry behavior');

    const ordered = await orderedSignatures(page);
    const baseIndex = Math.min(5, items.length - 7);
    const targetIndex = baseIndex + 6;
    const targetItem = items[targetIndex];
    const targetSignature = signatureForItem(targetItem);
    const targetPath = `/api/v1/thumbnails/${targetItem.sha256}`;

    await gotoIndexBySignature(page, ordered, baseIndex);

    let targetMode: 'fail' | 'success' = 'fail';
    let targetRequestCount = 0;
    await page.route((url: URL) => url.pathname === targetPath, async (route: Route) => {
      targetRequestCount += 1;
      if (targetMode === 'fail') {
        await route.fulfill({
          status: 404,
          contentType: 'text/plain',
          body: 'thumbnail missing',
        });
        return;
      }

      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fulfill({
        status: 200,
        contentType: 'image/png',
        body: Buffer.from(SUCCESS_PNG_BASE64, 'base64'),
      });
    });

    await gotoIndexBySignature(page, ordered, targetIndex);
    const failureBaseline = targetRequestCount;
    await expect
      .poll(async () => (await thumbStateForSignature(page, targetSignature))?.state ?? null, { timeout: 4000 })
      .toBe('error');

    const failedThumb = await thumbStateForSignature(page, targetSignature);
    expect(failedThumb).toBeTruthy();
    expect(failedThumb?.fallbackText).toBe(fallbackLabelForFilename(targetItem.filename));
    expect(failedThumb?.hasButton).toBe(false);
    const failedRequestDelta = targetRequestCount - failureBaseline;
    expect(failedRequestDelta).toBeGreaterThanOrEqual(0);
    expect(failedRequestDelta).toBeLessThanOrEqual(4);
    await page.waitForTimeout(500);
    expect(targetRequestCount - failureBaseline).toBe(failedRequestDelta);

    const beforeNav = await activeSignature(page);
    await pressStep(page, -1);
    const afterNav = await activeSignature(page);
    expect(afterNav).not.toBe(beforeNav);

    await gotoIndexBySignature(page, ordered, targetIndex - 6);
    await expect.poll(() => renderedSignatures(page), { timeout: 2000 }).not.toContain(targetSignature);

    targetMode = 'success';

    await gotoIndexBySignature(page, ordered, targetIndex - 5);
    const successBaseline = targetRequestCount;
    await expect
      .poll(async () => (await thumbStateForSignature(page, targetSignature))?.state ?? null, { timeout: 2500 })
      .toBe('loading');

    const loadingThumb = await thumbStateForSignature(page, targetSignature);
    expect(loadingThumb).toBeTruthy();
    expect(Math.abs((loadingThumb?.rect.width ?? 0) - (failedThumb?.rect.width ?? 0))).toBeLessThanOrEqual(1);
    expect(Math.abs((loadingThumb?.rect.height ?? 0) - (failedThumb?.rect.height ?? 0))).toBeLessThanOrEqual(1);

    await expect
      .poll(async () => (await thumbStateForSignature(page, targetSignature))?.state ?? null, { timeout: 5000 })
      .toBe('loaded');

    const loadedThumb = await thumbStateForSignature(page, targetSignature);
    expect(loadedThumb).toBeTruthy();
    const successRequestDelta = targetRequestCount - successBaseline;
    expect(successRequestDelta).toBeGreaterThanOrEqual(0);
    expect(successRequestDelta).toBeLessThanOrEqual(4);
    expect(Math.abs((loadedThumb?.rect.width ?? 0) - (failedThumb?.rect.width ?? 0))).toBeLessThanOrEqual(1);
    expect(Math.abs((loadedThumb?.rect.height ?? 0) - (failedThumb?.rect.height ?? 0))).toBeLessThanOrEqual(1);
  });
});
