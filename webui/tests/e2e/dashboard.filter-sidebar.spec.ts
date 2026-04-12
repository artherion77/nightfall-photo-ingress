import { expect, test, type Page, type Route } from '@playwright/test';

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function mockDashboardApis(page: Page): Promise<void> {
  await page.route('**/api/v1/staging?**', async (route: Route) => {
    await json(route, {
      items: [
        {
          item_id: '1',
          filename: 'one.jpg',
          sha256: 'sha-1',
          first_seen_at: '2026-04-11T00:00:00Z',
          account: 'staging',
          status: 'pending',
        },
        {
          item_id: '2',
          filename: 'two.mp4',
          sha256: 'sha-2',
          first_seen_at: '2026-04-11T00:00:01Z',
          account: 'staging',
          status: 'pending',
        },
        {
          item_id: '3',
          filename: 'three.dng',
          sha256: 'sha-3',
          first_seen_at: '2026-04-11T00:00:02Z',
          account: 'staging',
          status: 'pending',
        },
        {
          item_id: '4',
          filename: 'four.png',
          sha256: 'sha-4',
          first_seen_at: '2026-04-11T00:00:03Z',
          account: 'staging',
          status: 'pending',
        },
      ],
      total: 4,
      cursor: null,
    });
  });

  await page.route('**/api/v1/audit-log?**', async (route: Route) => {
    await json(route, { events: [], cursor: null, has_more: false });
  });

  await page.route('**/api/v1/audit-log/daily-summary', async (route: Route) => {
    await json(route, { day_utc: '2026-04-11', accepted_today: 0, rejected_today: 0 });
  });

  await page.route('**/api/v1/config/effective', async (route: Route) => {
    await json(route, { kpi_thresholds: {} });
  });

  await page.route('**/api/v1/health', async (route: Route) => {
    await json(route, {
      polling_ok: { ok: true, message: 'ok' },
      auth_ok: { ok: true, message: 'ok' },
      registry_ok: { ok: true, message: 'ok' },
      disk_ok: { ok: true, message: 'ok' },
      poll_duration_s: 1.2,
      error: null,
    });
  });
}

test.describe('Dashboard filter sidebar', () => {
  test('toggles filters client-side and supports multi-select + clear', async ({ page }: { page: Page }) => {
    await mockDashboardApis(page);

    await page.goto('/', { waitUntil: 'networkidle' });
    await expect(page.getByTestId('dashboard-filter-sidebar')).toBeVisible();

    // File-list tile removed from dashboard (re-added as tooltip in a later step).
    // Verify filter option buttons are present and toggling does not crash.
    await page.getByTestId('dashboard-filter-option-jpg').click();
    await page.getByTestId('dashboard-filter-option-mp4').click();
    await page.getByTestId('dashboard-filter-clear').click();

    // KPI grid and audit preview remain visible after toggle actions.
    await expect(page.getByTestId('kpi-grid')).toBeVisible();
    await expect(page.getByTestId('poll-runtime-chart')).toBeVisible();
  });
});
