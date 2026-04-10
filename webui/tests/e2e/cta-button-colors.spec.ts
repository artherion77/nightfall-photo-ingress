// @ts-nocheck
import { expect, test, type Page } from '@playwright/test';

async function waitForStagingData(page: Page): Promise<void> {
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/staging') && response.request().method() === 'GET',
  );
  await page.goto('/staging', { waitUntil: 'networkidle' });
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  await page.waitForSelector('[data-testid="triage-cta-accept"]');
  await page.waitForSelector('[data-testid="photo-card-details-trigger"]');
}

test.describe('Staging CTA Colors And Details Hover Geometry', () => {
  test('accept and reject hand icons match their button border colors', async ({ page }) => {
    await waitForStagingData(page);

    const metrics = await page.evaluate(() => {
      const read = (testId: string) => {
        const button = document.querySelector(`[data-testid="${testId}"]`) as HTMLElement | null;
        if (!button) return null;
        const icon = button.querySelector('.cta-icon') as HTMLElement | null;
        if (!icon) return null;
        const buttonStyle = window.getComputedStyle(button);
        const iconStyle = window.getComputedStyle(icon);
        return {
          borderColor: buttonStyle.borderTopColor,
          textColor: buttonStyle.color,
          iconColor: iconStyle.color,
        };
      };
      return {
        accept: read('triage-cta-accept'),
        reject: read('triage-cta-reject'),
      };
    });

    expect(metrics.accept).toBeTruthy();
    expect(metrics.reject).toBeTruthy();

    expect(metrics.accept!.textColor).toBe(metrics.accept!.borderColor);
    expect(metrics.accept!.iconColor).toBe(metrics.accept!.borderColor);

    expect(metrics.reject!.textColor).toBe(metrics.reject!.borderColor);
    expect(metrics.reject!.iconColor).toBe(metrics.reject!.borderColor);
  });

  test('details trigger hover activates on center circle and deactivates just outside circle', async ({ page }) => {
    await waitForStagingData(page);

    const trigger = page.locator('[data-testid="photo-card-details-trigger"]').first();
    const glyph = trigger.locator('.details-glyph');
    const popover = page.locator('[data-testid="photo-card-sidecar-popover"]').first();

    const box = await trigger.boundingBox();
    const glyphBox = await glyph.boundingBox();
    expect(box).toBeTruthy();
    expect(glyphBox).toBeTruthy();

    const centerX = box!.x + box!.width / 2;
    const centerY = box!.y + box!.height / 2;
    const radius = Math.min(box!.width, box!.height) / 2;

    const glyphCenterX = glyphBox!.x + glyphBox!.width / 2;
    const glyphCenterY = glyphBox!.y + glyphBox!.height / 2;
    const deltaX = Math.abs(glyphCenterX - centerX);
    const deltaY = Math.abs(glyphCenterY - centerY);
    expect(deltaX).toBeLessThanOrEqual(1.5);
    expect(deltaY).toBeLessThanOrEqual(1.5);

    const outsideX = centerX + radius + 40;
    const outsideY = centerY + radius + 20;

    await page.mouse.move(outsideX, outsideY);
    await expect(popover).toBeHidden();

    await trigger.hover({
      position: {
        x: box!.width / 2,
        y: box!.height / 2,
      },
    });
    await expect(popover).toBeVisible();
    await expect(trigger).toHaveClass(/is-sidecar-open/);

    await page.mouse.move(outsideX, outsideY);
    await expect(popover).toBeHidden();
  });
});
