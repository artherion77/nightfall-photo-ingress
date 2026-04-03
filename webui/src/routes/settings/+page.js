import { getEffectiveConfig } from '$lib/api/config';

export async function load() {
  const config = await getEffectiveConfig();
  return { config };
}
