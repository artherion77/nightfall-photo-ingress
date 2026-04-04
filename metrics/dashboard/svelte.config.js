let adapter = () => ({
  name: 'adapter-static-missing',
  adapt: async () => {
    throw new Error('adapter-static not installed; run npm install in metrics/dashboard');
  },
});

try {
  const mod = await import('@sveltejs/adapter-static');
  adapter = mod.default ?? mod;
} catch {
  // Keep fallback for local environments without node modules.
}

/** @type {import('@sveltejs/kit').Config} */
const config = {
  kit: {
    adapter: adapter({
      pages: '../../dashboard',
      assets: '../../dashboard',
      fallback: null,
      precompress: false,
      strict: true
    }),
    prerender: {
      handleHttpError: 'warn'
    }
  }
};

export default config;
