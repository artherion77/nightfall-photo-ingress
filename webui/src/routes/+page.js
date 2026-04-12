import { getAuditDailySummary, getAuditLog } from '$lib/api/audit';
import { getEffectiveConfig } from '$lib/api/config';
import { getStagingPage } from '$lib/api/staging';
import { getHealth, getPollHistory } from '$lib/api/health';

export async function load() {
  const [staging, audit, auditSummary, config, health, pollHistory] = await Promise.all([
    getStagingPage(null, 20),
    getAuditLog(null, 5),
    getAuditDailySummary(),
    getEffectiveConfig(),
    getHealth(),
    getPollHistory()
  ]);

  return { staging, audit, auditSummary, config, health, pollHistory };
}
