import { getAuditLog } from '$lib/api/audit';

export async function load() {
  const audit = await getAuditLog(null, 50);
  return { audit };
}
