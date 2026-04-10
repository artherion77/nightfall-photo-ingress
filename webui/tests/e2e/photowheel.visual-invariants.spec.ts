// @ts-nocheck
// Editor note: this file runs inside the dev-photo-ingress container with
// real Playwright types. The @ts-nocheck suppresses host-side implicit-any
// errors on inline callbacks (e.g. evaluate, waitForResponse) and test
// fixture parameters that arise because the playwright-shim.d.ts types
// all page methods and test args as `any`.
import { expect, test, type Page } from '@playwright/test';

type InputMode = 'keyboard' | 'wheel' | 'touch' | 'click';

type SlotMetrics = {
  signature: string;
  renderedPosition: number;
  active: boolean;
  rect: { left: number; right: number; width: number; height: number };
  center: number;
  opacity: number;
  blurPx: number;
  zIndex: number;
  transform: string;
  inlineTransform: string;
  transitionDuration: string;
  transitionTimingFunction: string;
  transitionProperty: string;
  display: string;
  visibility: string;
};

type WheelMetrics = {
  wheelRect: { left: number; right: number; width: number; height: number };
  wheelOverflow: string;
  itemCount: number;
  slots: SlotMetrics[];
  activePosition: number;
  activeSignature: string;
};

type TransitionSample = {
  activeCenter: number;
  activeTransform: string;
  activeOpacity: string;
  activeFilter: string;
};

function parseBlurPx(filter: string): number {
  const match = /blur\(([-\d.]+)px\)/.exec(filter);
  return match ? Number.parseFloat(match[1]) : 0;
}

function parseScale(transform: string): number {
  const match = /scale\(([-\d.]+)\)/.exec(transform);
  if (match) {
    return Number.parseFloat(match[1]);
  }

  const matrix3dMatch = /matrix3d\(([^)]+)\)/.exec(transform);
  if (matrix3dMatch) {
    const values = matrix3dMatch[1]
      .split(',')
      .map((v) => Number.parseFloat(v.trim()))
      .filter((v) => Number.isFinite(v));
    if (values.length === 16) {
      // Approximate uniform scale from X-axis basis vector length.
      const m11 = values[0];
      const m13 = values[2];
      return Math.hypot(m11, m13);
    }
  }

  const matrix2dMatch = /matrix\(([^)]+)\)/.exec(transform);
  if (matrix2dMatch) {
    const values = matrix2dMatch[1]
      .split(',')
      .map((v) => Number.parseFloat(v.trim()))
      .filter((v) => Number.isFinite(v));
    if (values.length === 6) {
      const a = values[0];
      const b = values[1];
      return Math.hypot(a, b);
    }
  }

  return 1;
}

function parseRotateY(transform: string): number {
  const match = /rotateY\(([-\d.]+)deg\)/.exec(transform);
  if (match) {
    return Number.parseFloat(match[1]);
  }

  const matrix3dMatch = /matrix3d\(([^)]+)\)/.exec(transform);
  if (matrix3dMatch) {
    const values = matrix3dMatch[1]
      .split(',')
      .map((v) => Number.parseFloat(v.trim()))
      .filter((v) => Number.isFinite(v));
    if (values.length === 16) {
      const m11 = values[0];
      const m13 = values[2];
      return (Math.atan2(-m13, m11) * 180) / Math.PI;
    }
  }

  return 0;
}

function centerTolerance(width: number): number {
  return Math.max(36, width * 0.18);
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

async function activeRenderedPosition(page: Page): Promise<number> {
  return page.evaluate(() => {
    const slots = Array.from(document.querySelectorAll('[data-testid="photo-wheel"] .slot')) as HTMLElement[];
    return slots.findIndex((slot) => slot.classList.contains('is-active'));
  });
}

async function pressStep(page: Page, mode: InputMode, direction: 1 | -1): Promise<void> {
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

  if (mode === 'click') {
    const position = await activeRenderedPosition(page);
    const targetPosition = position + direction;
    const clicked = await page.evaluate((requestedPosition) => {
      const slots = Array.from(document.querySelectorAll('[data-testid="photo-wheel"] .slot')) as HTMLElement[];
      if (requestedPosition < 0 || requestedPosition >= slots.length) {
        return false;
      }
      slots[requestedPosition].click();
      return true;
    }, targetPosition);
    if (!clicked) {
      return;
    }
    await page.waitForTimeout(260);
    return;
  }

  const wheel = page.locator('[data-testid="photo-wheel"]');
  const box = await wheel.boundingBox();
  if (!box) {
    throw new Error('photo wheel bounding box not available');
  }

  const y = box.y + box.height / 2;
  const startX = direction > 0 ? box.x + box.width * 0.85 : box.x + box.width * 0.15;
  const endX = direction > 0 ? box.x + box.width * 0.15 : box.x + box.width * 0.85;

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
  await page.waitForTimeout(360);
}

async function stepAndDetectChange(page: Page, mode: InputMode, direction: 1 | -1): Promise<boolean> {
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

async function stepUntilBoundary(page: Page, mode: InputMode, direction: 1 | -1): Promise<void> {
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

async function orderedSignatures(page: Page, mode: InputMode): Promise<string[]> {
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

async function gotoIndexBySignature(page: Page, ordered: string[], targetIndex: number): Promise<void> {
  const currentSig = await activeSignature(page);
  let currentIndex = ordered.indexOf(currentSig);
  if (currentIndex < 0) {
    throw new Error('active signature is not in ordered signature list');
  }

  for (let guard = 0; guard < 220 && currentIndex !== targetIndex; guard += 1) {
    const direction: 1 | -1 = targetIndex > currentIndex ? 1 : -1;
    const changed = await stepAndDetectChange(page, 'keyboard', direction);
    if (!changed) {
      break;
    }
    currentIndex = ordered.indexOf(await activeSignature(page));
  }

  expect(currentIndex).toBe(targetIndex);
}

async function collectWheelMetrics(page: Page): Promise<WheelMetrics> {
  return page.evaluate(() => {
    const wheel = document.querySelector('[data-testid="photo-wheel"]') as HTMLElement | null;
    if (!wheel) {
      throw new Error('photo wheel not found');
    }

    const wheelRect = wheel.getBoundingClientRect();
    const wheelStyle = getComputedStyle(wheel);
    const slots = Array.from(wheel.querySelectorAll('.slot')) as HTMLElement[];
    const metrics = slots.map((slot, renderedPosition) => {
      const rect = slot.getBoundingClientRect();
      const style = getComputedStyle(slot);
      const title = slot.querySelector('h3')?.textContent?.trim() ?? '';
      const shaLine = Array.from(slot.querySelectorAll('p'))
        .map((p) => p.textContent?.trim() ?? '')
        .find((line) => line.startsWith('SHA-256:')) ?? '';
      return {
        signature: `${title}|${shaLine}`,
        renderedPosition,
        active: slot.classList.contains('is-active'),
        rect: { left: rect.left, right: rect.right, width: rect.width, height: rect.height },
        center: rect.left + rect.width / 2,
        opacity: Number.parseFloat(style.opacity),
        blurPx: Number.parseFloat((/blur\(([-\d.]+)px\)/.exec(style.filter) ?? ['0', '0'])[1]),
        zIndex: Number.parseInt(style.zIndex || '0', 10),
        transform: style.transform,
        inlineTransform: slot.style.transform,
        transitionDuration: style.transitionDuration,
        transitionTimingFunction: style.transitionTimingFunction,
        transitionProperty: style.transitionProperty,
        display: style.display,
        visibility: style.visibility,
      };
    });

    const activePosition = metrics.findIndex((slot) => slot.active);
    if (activePosition < 0) {
      throw new Error('active slot not found');
    }

    return {
      wheelRect: { left: wheelRect.left, right: wheelRect.right, width: wheelRect.width, height: wheelRect.height },
      wheelOverflow: wheelStyle.overflow,
      itemCount: slots.length,
      slots: metrics,
      activePosition,
      activeSignature: metrics[activePosition].signature,
    } satisfies WheelMetrics;
  });
}

async function waitForWheelIdle(page: Page): Promise<void> {
  await expect
    .poll(
      async () =>
        (await page.locator('[data-testid="photo-wheel"]').getAttribute('data-interaction-state')) ?? 'unknown',
      { timeout: 1200 },
    )
    .toBe('IDLE');
}

async function sampleKeyboardTransition(page: Page): Promise<TransitionSample[]> {
  return page.evaluate(async () => {
    const wheel = document.querySelector('[data-testid="photo-wheel"]') as HTMLElement | null;
    if (!wheel) {
      throw new Error('photo wheel not found');
    }

    const samples: TransitionSample[] = [];
    let dispatched = false;
    const start = performance.now();
    while (performance.now() - start < 560) {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      if (!dispatched) {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        dispatched = true;
      }
      const active = wheel.querySelector('.slot.is-active') as HTMLElement | null;
      if (!active) {
        continue;
      }
      const rect = active.getBoundingClientRect();
      const style = getComputedStyle(active);
      samples.push({
        activeCenter: rect.left + rect.width / 2,
        activeTransform: style.transform,
        activeOpacity: style.opacity,
        activeFilter: style.filter,
      });
    }
    return samples;
  });
}

function assertMonotonicDegradation(metrics: WheelMetrics): void {
  const active = metrics.slots[metrics.activePosition];
  const leftNear = metrics.slots[metrics.activePosition - 1];
  const rightNear = metrics.slots[metrics.activePosition + 1];
  expect(leftNear).toBeTruthy();
  expect(rightNear).toBeTruthy();

  const nearSlots = [leftNear, rightNear];
  for (const near of nearSlots) {
    expect(parseScale(active.inlineTransform)).toBeGreaterThan(parseScale(near.inlineTransform));
    expect(Math.abs(parseRotateY(active.inlineTransform))).toBeLessThan(Math.abs(parseRotateY(near.inlineTransform)));
    expect(active.opacity).toBeGreaterThan(near.opacity);
    expect(parseBlurPx(active.transform === 'none' ? '' : active.transform)).toBeGreaterThanOrEqual(0);
    expect(active.blurPx).toBeLessThan(near.blurPx);
    expect(active.zIndex).toBeGreaterThan(near.zIndex);
  }

  const farLeft = metrics.slots[metrics.activePosition - 2];
  const farRight = metrics.slots[metrics.activePosition + 2];
  if (!farLeft || !farRight) {
    return;
  }

  for (const [near, far] of [
    [leftNear, farLeft],
    [rightNear, farRight],
  ] as const) {
    expect(parseScale(near.inlineTransform)).toBeGreaterThan(parseScale(far.inlineTransform));
    expect(Math.abs(parseRotateY(near.inlineTransform))).toBeLessThan(Math.abs(parseRotateY(far.inlineTransform)));
    expect(near.opacity).toBeGreaterThan(far.opacity);
    expect(near.blurPx).toBeLessThan(far.blurPx);
    expect(near.zIndex).toBeGreaterThan(far.zIndex);
  }
}

test.describe('PhotoWheel — Visual Invariants', () => {
  test('VIS-1 through VIS-7 hold on staging system data', async ({ page, browserName }, testInfo) => {
    test.skip(browserName !== 'chromium', 'suite targets Chromium only for deterministic geometry checks');

    await waitForAuthenticatedStagingData(page);
    const ordered = await orderedSignatures(page, 'keyboard');
    const total = ordered.length;
    expect(total).toBeGreaterThanOrEqual(3);

    const interiorIndex = total >= 5 ? Math.min(5, total - 3) : 1;
    await gotoIndexBySignature(page, ordered, interiorIndex);
    const metrics = await collectWheelMetrics(page);
    const active = metrics.slots[metrics.activePosition];
    const activeCenterDelta = Math.abs(active.center - (metrics.wheelRect.left + metrics.wheelRect.width / 2));

    testInfo.annotations.push({ type: 'staging-item-count', description: String(total) });
    if (total < 50) {
      testInfo.annotations.push({
        type: 'coverage-limit',
        description: `live staging exposes ${total} items; the >50 item envelope remains environment-limited`,
      });
    }

    expect(activeCenterDelta).toBeLessThanOrEqual(centerTolerance(active.rect.width));
    expect(active.zIndex).toBeGreaterThan(Math.max(...metrics.slots.filter((slot) => !slot.active).map((slot) => slot.zIndex)));

    const centerElementClass = await page.evaluate(() => {
      const wheel = document.querySelector('[data-testid="photo-wheel"]') as HTMLElement | null;
      if (!wheel) {
        return null;
      }
      const rect = wheel.getBoundingClientRect();
      const element = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2) as HTMLElement | null;
      return element?.closest('.slot')?.className ?? null;
    });
    expect(centerElementClass).toContain('is-active');

    const leftNear = metrics.slots[metrics.activePosition - 1];
    const rightNear = metrics.slots[metrics.activePosition + 1];
    expect(leftNear).toBeTruthy();
    expect(rightNear).toBeTruthy();
    const leftOverlap = leftNear.rect.right - active.rect.left;
    const rightOverlap = active.rect.right - rightNear.rect.left;
    expect(leftOverlap).toBeGreaterThan(0);
    expect(rightOverlap).toBeGreaterThan(0);
    expect(leftNear.zIndex).toBeLessThan(active.zIndex);
    expect(rightNear.zIndex).toBeLessThan(active.zIndex);

    assertMonotonicDegradation(metrics);

    const transitionSamples = await sampleKeyboardTransition(page);
    expect(transitionSamples.length).toBeGreaterThan(10);
    const uniqueTransforms = new Set(transitionSamples.map((sample) => sample.activeTransform));
    expect(uniqueTransforms.size).toBeGreaterThan(6);
    let maxFrameJump = 0;
    for (let i = 1; i < transitionSamples.length; i += 1) {
      maxFrameJump = Math.max(
        maxFrameJump,
        Math.abs(transitionSamples[i].activeCenter - transitionSamples[i - 1].activeCenter),
      );
    }
    expect(maxFrameJump).toBeLessThanOrEqual(90);

    expect(active.transitionProperty).toContain('transform');
    expect(active.transitionProperty).toContain('opacity');
    expect(active.transitionProperty).toContain('filter');
    expect(active.transitionDuration).toContain('0.35s');
    expect(active.transitionTimingFunction).toContain('cubic-bezier(0.2, 0, 0, 1)');

    const farLeft = metrics.slots[metrics.activePosition - 2];
    const farRight = metrics.slots[metrics.activePosition + 2];
    expect(Math.abs((active.center - leftNear.center) - (rightNear.center - active.center))).toBeLessThanOrEqual(16);
    expect(leftNear.opacity).toBeCloseTo(rightNear.opacity, 3);
    expect(leftNear.blurPx).toBeCloseTo(rightNear.blurPx, 3);
    expect(leftNear.zIndex).toBe(rightNear.zIndex);
    expect(Math.abs(parseRotateY(leftNear.inlineTransform))).toBeCloseTo(
      Math.abs(parseRotateY(rightNear.inlineTransform)),
      3,
    );

    if (farLeft && farRight) {
      expect(Math.abs((active.center - farLeft.center) - (farRight.center - active.center))).toBeLessThanOrEqual(22);
      expect(farLeft.opacity).toBeCloseTo(farRight.opacity, 3);
      expect(farLeft.blurPx).toBeCloseTo(farRight.blurPx, 3);
      expect(farLeft.zIndex).toBe(farRight.zIndex);
      expect(Math.abs(parseRotateY(farLeft.inlineTransform))).toBeCloseTo(
        Math.abs(parseRotateY(farRight.inlineTransform)),
        3,
      );
    }

    expect(metrics.wheelOverflow).toBe('hidden');
    const edgeSlots = [metrics.slots[0], metrics.slots[metrics.slots.length - 1]];
    const clippedEdge = edgeSlots.find(
      (slot) => slot.rect.left < metrics.wheelRect.left || slot.rect.right > metrics.wheelRect.right,
    );
    expect(clippedEdge).toBeTruthy();
    expect(clippedEdge?.display).not.toBe('none');
    expect(clippedEdge?.visibility).not.toBe('hidden');
  });

  test('wheel and keyboard navigation preserve the animated visual contract', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === 'mobile-chromium', 'wheel assertions are desktop/tablet-oriented');

    await waitForAuthenticatedStagingData(page);
    const ordered = await orderedSignatures(page, 'keyboard');
    test.skip(ordered.length < 3, 'need at least three items for wheel and click assertions');

    await gotoIndexBySignature(page, ordered, Math.min(3, ordered.length - 2));
    const beforeWheel = await collectWheelMetrics(page);
    await pressStep(page, 'wheel', 1);
    const afterWheel = await collectWheelMetrics(page);
    expect(afterWheel.activeSignature).not.toBe(beforeWheel.activeSignature);
    expect(afterWheel.slots[afterWheel.activePosition].transitionDuration).toContain('0.35s');
    expect(afterWheel.slots[afterWheel.activePosition].transitionTimingFunction).toContain('cubic-bezier(0.2, 0, 0, 1)');

    await waitForWheelIdle(page);
    const beforeKeyboard = await collectWheelMetrics(page);
    const keyboardChanged = await stepAndDetectChange(page, 'keyboard', -1);
    expect(keyboardChanged).toBeTruthy();
    await waitForWheelIdle(page);
    const afterKeyboard = await collectWheelMetrics(page);
    expect(afterKeyboard.activeSignature).not.toBe(beforeKeyboard.activeSignature);
    expect(afterKeyboard.slots[afterKeyboard.activePosition].transitionDuration).toContain('0.35s');
    expect(afterKeyboard.slots[afterKeyboard.activePosition].transitionTimingFunction).toContain('cubic-bezier(0.2, 0, 0, 1)');
  });

  test('touch navigation preserves the animated visual contract', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile-chromium', 'touch assertions run on mobile profile only');

    await waitForAuthenticatedStagingData(page);
    const ordered = await orderedSignatures(page, 'keyboard');
    test.skip(ordered.length < 3, 'need at least three items for touch assertions');

    await gotoIndexBySignature(page, ordered, Math.min(3, ordered.length - 2));
    const beforeTouch = await collectWheelMetrics(page);
    const touchChanged = await stepAndDetectChange(page, 'touch', 1);
    expect(touchChanged).toBeTruthy();
    const afterTouch = await collectWheelMetrics(page);
    expect(afterTouch.activeSignature).not.toBe(beforeTouch.activeSignature);
    expect(afterTouch.slots[afterTouch.activePosition].transitionDuration).toContain('0.35s');
    expect(afterTouch.slots[afterTouch.activePosition].transitionTimingFunction).toContain('cubic-bezier(0.2, 0, 0, 1)');
  });
});