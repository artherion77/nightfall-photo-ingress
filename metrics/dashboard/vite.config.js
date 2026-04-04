let defineConfig = (config) => config;
let sveltekit = () => ({ name: 'sveltekit-plugin-missing' });

try {
  ({ defineConfig } = await import('vite'));
} catch {
  // Keep fallback for local environments without node modules.
}

try {
  ({ sveltekit } = await import('@sveltejs/kit/vite'));
} catch {
  // Keep fallback for local environments without node modules.
}

export default defineConfig({
  plugins: [sveltekit()],
});
