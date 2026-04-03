import { getBlocklist } from '$lib/api/blocklist';

export async function load() {
  const blocklist = await getBlocklist();
  return { blocklist };
}
