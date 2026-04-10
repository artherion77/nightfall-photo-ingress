// @ts-nocheck
// Editor note: this file runs inside the dev-photo-ingress container with
// real Playwright types. The @ts-nocheck suppresses host-side implicit-any
// errors on inline callbacks (e.g. waitForResponse, evaluate) that arise
// because the playwright-shim.d.ts types page methods as `any`.
import { expect, test, type Page } from '@playwright/test';

type WheelSnapshot = {
  signature: string;
  activeCenter: number;
  wheelCenter: number;
  activeWidth: number;
  gap: number;
  leftRendered: number;
  rightRendered: number;
  stagePosition: string;
  stageTransform: string;
  wheelScrollLeft: number;
  pairSymmetric: boolean;
};

const RENDER_RADIUS = 5;

function centralThirdBounds(wheelRect: { left: number; width: number }) {
  return {
    min: wheelRect.left + wheelRect.width / 3,
    max: wheelRect.left + (2 * wheelRect.width) / 3,
  };
}

async function waitForAuthenticatedStagingData(page: Page): Promise<void> {
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/staging') && response.request().method() === 'GET',
  );
  await page.goto('/staging', { waitUntil: 'networkidle' });
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const payload = (await response.json()) as { items?: unknown[] };
  expect(Array.isArray(payload.items)).toBeTruthy();
  expect((payload.items ?? []).length).toBeGreaterThan(1);
  await page.waitForSelector('[data-testid="photo-wheel"] .slot.is-active');
  await page.waitForTimeout(280);
}

async function activeSignature(page: Page): Promise<string> {
  return page.locator('[data-testid="photo-wheel"] .slot.is-active').evaluate((node) => {
    const title = node.querySelector('h3')?.textContent?.trim() ?? '';
    const shaLine = Array.from(node.querySelectorAll('p'))
      .map((p) => p.textContent?.trim() ?? '')
      .find((line) => line.startsWith('SHA-256:')) ?? '';
    return `${title}|${shaLine}`;
  });
}

async function pressStep(page: Page, mode: 'keyboard' | 'wheel' | 'touch', direction: 1 | -1): Promise<void> {
  if (mode === 'keyboard') {
    await page.keyboard.press(direction > 0 ? 'ArrowRight' : 'ArrowLeft');
    await page.waitForTimeout(220);
    return;
  }

  if (mode === 'wheel') {
    await page.locator('[data-testid="photo-wheel"]').hover();
    await page.mouse.wheel(0, direction > 0 ? 70 : -70);
    await page.waitForTimeout(260);
    return;
  }

  const wheel = page.locator('[data-testid="photo-wheel"]');
  const box = await wheel.boundingBox();
  if (!box) {
    throw new Error('photo wheel bounding box not available');
  }

  const y = box.y + box.height / 2;
  const startX = direction > 0 ? box.x + box.width * 0.75 : box.x + box.width * 0.25;
  const endX = direction > 0 ? box.x + box.width * 0.25 : box.x + box.width * 0.75;

  const session = await page.context().newCDPSession(page);
  await session.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: [{ x: Math.round(startX), y: Math.round(y) }],
  });

  const steps = 10;
  for (let i = 1; i <= steps; i += 1) {
    const x = startX + ((endX - startX) * i) / steps;
    await session.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: Math.round(x), y: Math.round(y) }],
    });
  }

  await session.send('Input.dispatchTouchEvent', {
    type: 'touchEnd',
    touchPoints: [],
  });
  await session.detach();
  await page.waitForTimeout(300);
}

async function stepUntilBoundary(page: Page, mode: 'keyboard' | 'wheel' | 'touch', direction: 1 | -1): Promise<void> {
  let stableCount = 0;
  let last = await activeSignature(page);
  for (let i = 0; i < 80; i += 1) {
    await pressStep(page, mode, direction);
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

async function stepAndDetectChange(page: Page, mode: 'keyboard' | 'wheel' | 'touch', direction: 1 | -1): Promise<boolean> {
  const before = await activeSignature(page);
  for (let i = 0; i < 4; i += 1) {
    await pressStep(page, mode, direction);
    const after = await activeSignature(page);
    if (after !== before) {
      return true;
    }
  }
  return false;
}

async function orderedSignatures(page: Page, mode: 'keyboard' | 'wheel' | 'touch'): Promise<string[]> {
  await stepUntilBoundary(page, mode, -1);

  const signatures: string[] = [await activeSignature(page)];
  for (let i = 0; i < 220; i += 1) {
    const changed = await stepAndDetectChange(page, mode, 1);
    if (!changed) {
      break;
    }
    signatures.push(await activeSignature(page));
  }

  await stepUntilBoundary(page, mode, -1);
  return signatures;
}

async function snapshot(page: Page): Promise<WheelSnapshot> {
  return page.evaluate(() => {
    const parseScale = (transform: string): number => {
      const match = /scale\(([-\d.]+)\)/.exec(transform);
      return match ? Number.parseFloat(match[1]) : 1;
    };

    const parseRotateY = (transform: string): number => {
      const match = /rotateY\(([-\d.]+)deg\)/.exec(transform);
      return match ? Number.parseFloat(match[1]) : 0;
    };

    const parseTranslateZ = (transform: string): number => {
      const match = /translateZ\(([-\d.]+)px\)/.exec(transform);
      return match ? Number.parseFloat(match[1]) : 0;
    };

    const wheel = document.querySelector('[data-testid="photo-wheel"]') as HTMLElement | null;
    if (!wheel) {
      throw new Error('photo wheel not found');
    }

    const stage = wheel.querySelector('.stage') as HTMLElement | null;
    const slots = Array.from(wheel.querySelectorAll('.slot')) as HTMLElement[];
    const active = wheel.querySelector('.slot.is-active') as HTMLElement | null;
    if (!stage || !active) {
      throw new Error('stage or active slot not found');
    }

    const wheelRect = wheel.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    const stageStyle = getComputedStyle(stage);

    const activePos = slots.indexOf(active);
    const leftRendered = activePos;
    const rightRendered = slots.length - activePos - 1;

    const pairCount = Math.min(leftRendered, rightRendered);
    let pairSymmetric = true;
    for (let offset = 1; offset <= pairCount; offset += 1) {
      const left = slots[activePos - offset];
      const right = slots[activePos + offset];
      const ls = getComputedStyle(left);
      const rs = getComputedStyle(right);
      const scaleDelta = Math.abs(parseScale(left.style.transform) - parseScale(right.style.transform));
      const rotateAbsDelta = Math.abs(
        Math.abs(parseRotateY(left.style.transform)) - Math.abs(parseRotateY(right.style.transform))
      );
      const translateZDelta = Math.abs(parseTranslateZ(left.style.transform) - parseTranslateZ(right.style.transform));
      if (
        ls.opacity !== rs.opacity ||
        ls.filter !== rs.filter ||
        ls.zIndex !== rs.zIndex ||
        scaleDelta > 0.001 ||
        rotateAbsDelta > 0.001 ||
        translateZDelta > 0.001
      ) {
        pairSymmetric = false;
        break;
      }
    }

    const title = active.querySelector('h3')?.textContent?.trim() ?? '';
    const shaLine = Array.from(active.querySelectorAll('p'))
      .map((p) => p.textContent?.trim() ?? '')
      .find((line) => line.startsWith('SHA-256:')) ?? '';

    return {
      signature: `${title}|${shaLine}`,
      activeCenter: activeRect.left + activeRect.width / 2,
      wheelCenter: wheelRect.left + wheelRect.width / 2,
      activeWidth: activeRect.width,
      gap: Number.parseFloat(stageStyle.getPropertyValue('--slot-gap') || '0') || 0,
      leftRendered,
      rightRendered,
      stagePosition: stageStyle.position,
      stageTransform: stageStyle.transform,
      wheelScrollLeft: wheel.scrollLeft,
      pairSymmetric,
    } satisfies WheelSnapshot;
  });
}

async function gotoIndexBySignature(
  page: Page,
  mode: 'keyboard' | 'wheel' | 'touch',
  ordered: string[],
  targetIndex: number,
): Promise<void> {
  const currentSig = await activeSignature(page);
  let currentIndex = ordered.indexOf(currentSig);
  if (currentIndex < 0) {
    throw new Error('active signature is not in ordered signature list');
  }

  for (let guard = 0; guard < 220 && currentIndex !== targetIndex; guard += 1) {
    const direction: 1 | -1 = targetIndex > currentIndex ? 1 : -1;
    const changed = await stepAndDetectChange(page, mode, direction);
    if (!changed) {
      break;
    }
    currentIndex = ordered.indexOf(await activeSignature(page));
  }

  expect(currentIndex).toBe(targetIndex);
}

test.describe('PhotoWheel — Centering Invariant (Perceptual)', () => {
  test('CTR-1 through CTR-6 via keyboard on staging system data', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'suite targets Chromium only for deterministic geometry checks');

    await waitForAuthenticatedStagingData(page);
    const ordered = await orderedSignatures(page, 'keyboard');
    const total = ordered.length;
    expect(total).toBeGreaterThanOrEqual(2);

    const haveInterior = total >= 2 * RENDER_RADIUS + 1;
    test.skip(!haveInterior, `need at least ${2 * RENDER_RADIUS + 1} staging items to assert interior invariants`);

    await gotoIndexBySignature(page, 'keyboard', ordered, 0);
    const lowBoundary = await snapshot(page);

    await gotoIndexBySignature(page, 'keyboard', ordered, RENDER_RADIUS);
    const interior = await snapshot(page);

    await gotoIndexBySignature(page, 'keyboard', ordered, total - 1);
    const highBoundary = await snapshot(page);

    const interiorDelta = Math.abs(interior.activeCenter - interior.wheelCenter);
    const lowDelta = Math.abs(lowBoundary.activeCenter - lowBoundary.wheelCenter);
    const highDelta = Math.abs(highBoundary.activeCenter - highBoundary.wheelCenter);

    expect(Math.abs(interior.leftRendered - interior.rightRendered)).toBe(0);

    expect(interiorDelta).toBeLessThanOrEqual(4);
    expect(lowDelta).toBeLessThanOrEqual(4);
    expect(highDelta).toBeLessThanOrEqual(4);
    expect(interior.pairSymmetric).toBeTruthy();

    await gotoIndexBySignature(page, 'keyboard', ordered, RENDER_RADIUS - 1);
    const sampled = await page.evaluate(async () => {
      const centers: number[] = [];
      const wheel = document.querySelector('[data-testid="photo-wheel"]') as HTMLElement;
      const keyPromise = (async () => {
        const event = new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true });
        window.dispatchEvent(event);
      })();

      const start = performance.now();
      while (performance.now() - start < 520) {
        await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
        const active = wheel.querySelector('.slot.is-active') as HTMLElement | null;
        if (!active) continue;
        const rect = active.getBoundingClientRect();
        centers.push(rect.left + rect.width / 2);
      }
      await keyPromise;
      return centers;
    });

    let maxFrameJump = 0;
    for (let i = 1; i < sampled.length; i += 1) {
      maxFrameJump = Math.max(maxFrameJump, Math.abs(sampled[i] - sampled[i - 1]));
    }
    expect(maxFrameJump).toBeLessThanOrEqual(80);

    expect(interior.stagePosition).toBe('relative');
    expect(interior.stageTransform).toBe('none');
    expect(lowBoundary.wheelScrollLeft).toBe(0);
    expect(interior.wheelScrollLeft).toBe(0);
    expect(highBoundary.wheelScrollLeft).toBe(0);
  });

  test('mouse wheel navigation preserves non-corrective centering contract', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'mobile-chromium', 'wheel assertions are desktop/tablet-oriented');

    await waitForAuthenticatedStagingData(page);
    const ordered = await orderedSignatures(page, 'wheel');
    test.skip(ordered.length < 2, 'need at least two items for wheel assertions');

    const before = await snapshot(page);
    await pressStep(page, 'wheel', 1);
    const after = await snapshot(page);

    expect(before.stagePosition).toBe('relative');
    expect(after.stagePosition).toBe('relative');
    expect(before.stageTransform).toBe('none');
    expect(after.stageTransform).toBe('none');
    expect(before.wheelScrollLeft).toBe(0);
    expect(after.wheelScrollLeft).toBe(0);
    expect(after.signature).not.toBe(before.signature);
  });

  test('touch navigation preserves non-corrective centering contract', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile-chromium', 'touch assertions run on mobile profile only');

    await waitForAuthenticatedStagingData(page);
    const ordered = await orderedSignatures(page, 'touch');
    test.skip(ordered.length < 2, 'need at least two items for touch assertions');

    const before = await snapshot(page);
    await pressStep(page, 'touch', 1);
    const after = await snapshot(page);

    expect(before.stagePosition).toBe('relative');
    expect(after.stagePosition).toBe('relative');
    expect(before.stageTransform).toBe('none');
    expect(after.stageTransform).toBe('none');
    expect(before.wheelScrollLeft).toBe(0);
    expect(after.wheelScrollLeft).toBe(0);
  });
});
