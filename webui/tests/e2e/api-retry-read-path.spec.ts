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

async function json(route: Route, body: unknown, status = 200, headers: Record<string, string> = {}) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers,
    body: JSON.stringify(body),
  });
}

async function openAudit(page: Page) {
  await page.goto('/audit', { waitUntil: 'networkidle' });
}

test.describe('C9 read-path retry/backoff validation', () => {
  test('retries GET on 503 with bounded backoff and eventually renders', async ({ page }: { page: Page }) => {
    let attempts = 0;
    const observedMs: number[] = [];
    const firstPage = Array.from({ length: 50 }, (_, idx) => buildEvent(300 - idx));

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      observedMs.push(Date.now());
      attempts += 1;
      if (attempts <= 2) {
        await json(route, { detail: 'temporarily unavailable' }, 503);
        return;
      }
      await json(route, { events: firstPage, cursor: null, has_more: false });
    });

    await openAudit(page);

    expect(attempts).toBe(3);
    expect(observedMs[1] - observedMs[0]).toBeGreaterThanOrEqual(400);
    expect(observedMs[2] - observedMs[1]).toBeGreaterThanOrEqual(850);
    await expect(page.getByTestId('audit-event')).toHaveCount(50);
    await expect(page.getByTestId('audit-load-error')).toHaveCount(0);
  });

  test('honors Retry-After for 429 before retrying GET', async ({ page }: { page: Page }) => {
    let attempts = 0;
    const observedMs: number[] = [];
    const firstPage = Array.from({ length: 50 }, (_, idx) => buildEvent(250 - idx));

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      observedMs.push(Date.now());
      attempts += 1;
      if (attempts === 1) {
        await json(route, { detail: 'rate limited' }, 429, { 'Retry-After': '1' });
        return;
      }
      await json(route, { events: firstPage, cursor: null, has_more: false });
    });

    await openAudit(page);

    expect(attempts).toBe(2);
    expect(observedMs[1] - observedMs[0]).toBeGreaterThanOrEqual(950);
    await expect(page.getByTestId('audit-event')).toHaveCount(50);
  });

  test('retries network errors and recovers without duplicate overlap', async ({ page }: { page: Page }) => {
    let attempts = 0;
    const firstPage = Array.from({ length: 50 }, (_, idx) => buildEvent(200 - idx));

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      attempts += 1;
      if (attempts === 1) {
        await route.abort('failed');
        return;
      }
      await json(route, { events: firstPage, cursor: '151', has_more: true });
    });

    await openAudit(page);
    await expect(page.getByTestId('audit-event')).toHaveCount(50);

    let overlapCalls = 0;
    let maxInFlight = 0;
    let inFlight = 0;
    await page.unroute('**/api/v1/audit-log?**');
    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      const url = new URL(route.request().url());
      const after = url.searchParams.get('after');
      if (!after) {
        await json(route, { events: firstPage, cursor: '151', has_more: true });
        return;
      }
      overlapCalls += 1;
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((resolve) => setTimeout(resolve, 350));
      inFlight -= 1;
      await json(route, { events: [], cursor: null, has_more: false });
    });

    const sentinel = page.getByTestId('audit-timeline-sentinel');
    await sentinel.scrollIntoViewIfNeeded();
    await sentinel.scrollIntoViewIfNeeded();
    await sentinel.scrollIntoViewIfNeeded();

    await expect(page.getByTestId('audit-end-marker')).toBeVisible();
    expect(overlapCalls).toBe(1);
    expect(maxInFlight).toBe(1);
  });

  test('surfaces error after retry exhaustion and exits loading state', async ({ page }: { page: Page }) => {
    const firstPage = Array.from({ length: 50 }, (_, idx) => buildEvent(100 - idx));
    let secondaryAttempts = 0;

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      const url = new URL(route.request().url());
      const after = url.searchParams.get('after');
      if (!after) {
        await json(route, { events: firstPage, cursor: '51', has_more: true });
        return;
      }
      secondaryAttempts += 1;
      await json(route, { detail: 'upstream unavailable' }, 503);
    });

    await openAudit(page);
    await expect(page.getByTestId('audit-event')).toHaveCount(50);

    await page.getByTestId('audit-timeline-sentinel').scrollIntoViewIfNeeded();

    expect(secondaryAttempts).toBe(4);
    await expect(page.getByTestId('audit-load-error')).toBeVisible();
    await expect(page.getByTestId('audit-scroll-hint')).toHaveText('Scroll to load more');
    await expect(page.getByTestId('audit-event')).toHaveCount(50);
  });

  test('does not retry non-retryable 4xx GET failures', async ({ page }: { page: Page }) => {
    let attempts = 0;

    await page.route('**/api/v1/audit-log?**', async (route: Route) => {
      attempts += 1;
      await json(route, { detail: 'forbidden' }, 403);
    });

    await page.goto('/audit');

    expect(attempts).toBe(1);
    await expect(page.locator('h1')).toHaveText('Something went wrong');
  });
});
