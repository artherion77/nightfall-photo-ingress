import { getStagingPage } from '$lib/api/staging';

export async function load() {
  const staging = await getStagingPage(null, 20);
  return { staging };
}
