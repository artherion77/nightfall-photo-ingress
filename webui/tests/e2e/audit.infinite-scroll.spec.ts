import { expect, test, type Page, type Route } from '@playwright/test';

function buildEvent(id: number) {
  return {
    id,
    action: id % 2 === 0 ? 'accepted' : 'rejected',
    description: `event-${id}`,
    ts: `2026-04-12T00:00:${String(id % 60).padStart(2, '0')}Z`,
    actor: 'api',
    sha256: `sha-${id}`,
    account_name: 'staging',
    filename: `file-${id}.jpg`,
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

test.describe('Audit Timeline infinite scroll', () => {
  test('loads first page and appends next page when scroll reaches sentinel', async ({ page }: { page: Page }) => {
    const firstPage = Array.from({ length: 50 }, (_, idx) => buildEvent(200 - idx));
    const secondPage = Array.from({ length: 50 }, (_, idx) => buildEvent(150 - idx));

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      const url = new URL(route.request().url());
      const after = url.searchParams.get('after');
      if (!after) {
        await json(route, { events: firstPage, cursor: '151', has_more: true });
        return;
      }
      await json(route, { events: secondPage, cursor: null, has_more: false });
    });

    await page.goto('/audit', { waitUntil: 'networkidle' });

    await expect(page.getByTestId('audit-event')).toHaveCount(50);
    await expect(page.getByTestId('audit-scroll-hint')).toBeVisible();

    await page.getByTestId('audit-timeline-sentinel').scrollIntoViewIfNeeded();

    await expect(page.getByTestId('audit-event')).toHaveCount(100);
    await expect(page.getByTestId('audit-end-marker')).toHaveText('End of timeline');
  });

  test('shows terminal marker and does not request additional pages at end', async ({ page }: { page: Page }) => {
    let requests = 0;
    const firstPage = Array.from({ length: 50 }, (_, idx) => buildEvent(100 - idx));

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      requests += 1;
      await json(route, { events: firstPage, cursor: null, has_more: false });
    });

    await page.goto('/audit', { waitUntil: 'networkidle' });

    await expect(page.getByTestId('audit-event')).toHaveCount(50);
    await expect(page.getByTestId('audit-end-marker')).toBeVisible();
    await expect(page.getByTestId('audit-timeline-sentinel')).toHaveCount(0);
    expect(requests).toBe(1);
  });

  test('keeps existing entries and surfaces error when infinite load fails', async ({ page }: { page: Page }) => {
    const firstPage = Array.from({ length: 50 }, (_, idx) => buildEvent(200 - idx));

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      const url = new URL(route.request().url());
      const after = url.searchParams.get('after');
      if (!after) {
        await json(route, { events: firstPage, cursor: '151', has_more: true });
        return;
      }
      await json(route, { detail: 'upstream unavailable' }, 503);
    });

    await page.goto('/audit', { waitUntil: 'networkidle' });
    await expect(page.getByTestId('audit-event')).toHaveCount(50);

    await page.getByTestId('audit-timeline-sentinel').scrollIntoViewIfNeeded();

    await expect(page.getByTestId('audit-load-error')).toBeVisible();
    await expect(page.getByTestId('audit-event')).toHaveCount(50);
    await expect(page.getByTestId('audit-scroll-hint')).toBeVisible();
  });
});
