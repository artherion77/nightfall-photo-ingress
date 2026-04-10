// @ts-nocheck
import { expect, test, type Page } from '@playwright/test';

async function waitForStagingData(page: Page): Promise<void> {
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/v1/staging') && response.request().method() === 'GET',
  );
  await page.goto('/staging', { waitUntil: 'networkidle' });
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  await page.waitForSelector('[data-testid="photo-wheel"] .slot.is-active [data-testid="photo-card"]');
  await page.waitForSelector('[data-testid="photo-card-action-accept"]');
  await page.waitForSelector('[data-testid="photo-card-action-reject"]');
}

test.describe('PhotoCard Action Buttons', () => {
  test('renders action buttons only for active card', async ({ page }) => {
    await waitForStagingData(page);

    const actions = page.locator('[data-testid="photo-card-actions"]');
    await expect(actions).toHaveCount(1);

    await expect(page.locator('[data-testid="photo-card-action-accept"]')).toHaveText('Accept');
    await expect(page.locator('[data-testid="photo-card-action-reject"]')).toHaveText('Reject');
  });

  test('positions action buttons to the right of active card and vertically stacked', async ({ page }) => {
    await waitForStagingData(page);

    const activeCard = page.locator('[data-testid="photo-wheel"] .slot.is-active [data-testid="photo-card"]').first();
    const acceptBtn = page.locator('[data-testid="photo-card-action-accept"]').first();
    const rejectBtn = page.locator('[data-testid="photo-card-action-reject"]').first();

    const [cardBox, acceptBox, rejectBox] = await Promise.all([
      activeCard.boundingBox(),
      acceptBtn.boundingBox(),
      rejectBtn.boundingBox(),
    ]);

    expect(cardBox).toBeTruthy();
    expect(acceptBox).toBeTruthy();
    expect(rejectBox).toBeTruthy();

    expect(acceptBox!.x).toBeGreaterThan(cardBox!.x + cardBox!.width);
    expect(Math.abs(acceptBox!.x - rejectBox!.x)).toBeLessThanOrEqual(2);
    expect(acceptBox!.y).toBeLessThan(rejectBox!.y);
  });

  test('keeps consistent horizontal spacing from active card border', async ({ page }) => {
    await waitForStagingData(page);

    const activeCard = page.locator('[data-testid="photo-wheel"] .slot.is-active [data-testid="photo-card"]').first();
    const acceptBtn = page.locator('[data-testid="photo-card-action-accept"]').first();

    const [cardBox, acceptBox] = await Promise.all([activeCard.boundingBox(), acceptBtn.boundingBox()]);
    expect(cardBox).toBeTruthy();
    expect(acceptBox).toBeTruthy();

    const horizontalGap = acceptBox!.x - (cardBox!.x + cardBox!.width);
    expect(horizontalGap).toBeGreaterThanOrEqual(6);
    expect(horizontalGap).toBeLessThanOrEqual(32);
  });
});
