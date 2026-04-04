import adapter from '@sveltejs/adapter-static';

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
