import { getAuditLog } from '$lib/api/audit';
import { getEffectiveConfig } from '$lib/api/config';
import { getStagingPage } from '$lib/api/staging';
import { getHealth } from '$lib/api/health';

export async function load() {
  const [staging, audit, config, health] = await Promise.all([
    getStagingPage(null, 20),
    getAuditLog(null, 5),
    getEffectiveConfig(),
    getHealth()
  ]);

  return { staging, audit, config, health };
}
