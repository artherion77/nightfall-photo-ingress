import { sveltekit } from '@sveltejs/kit/vite';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { brotliCompressSync, gzipSync } from 'node:zlib';
import { visualizer } from 'rollup-plugin-visualizer';
import { defineConfig } from 'vite';

function emitBundleStats() {
  const collectedChunks = [];

  return {
    name: 'emit-bundle-stats',
    buildStart() {
      collectedChunks.length = 0;
    },
    generateBundle(outputOptions, bundle) {
      for (const [fileName, output] of Object.entries(bundle)) {
        if (output.type === 'chunk') {
          const code = output.code || '';
          const rawBytes = Buffer.byteLength(code, 'utf8');
          const gzipBytes = gzipSync(code).length;
          const brotliBytes = brotliCompressSync(code).length;
          const modules = Object.entries(output.modules || {})
            .map(([id, mod]) => ({
              id,
              rendered_bytes: Math.max(0, Math.round(mod?.renderedLength || 0))
            }))
            .sort((a, b) => b.rendered_bytes - a.rendered_bytes);

          collectedChunks.push({
            name: fileName,
            type: 'js',
            raw_bytes: rawBytes,
            gzip_bytes: gzipBytes,
            brotli_bytes: brotliBytes,
            modules
          });
        } else if (output.type === 'asset') {
          const source = output.source;
          const bytes = source instanceof Uint8Array
            ? Buffer.from(source)
            : Buffer.from(String(source || ''), 'utf8');
          collectedChunks.push({
            name: fileName,
            type: 'asset',
            raw_bytes: bytes.length,
            gzip_bytes: gzipSync(bytes).length,
            brotli_bytes: brotliCompressSync(bytes).length,
            modules: []
          });
        }
      }

      const outDir = outputOptions.dir || '';
      const outBase = outDir.replace(/\\/g, '/');
      if (!outBase.includes('/.svelte-kit/output/client/')) {
        return;
      }
    },
    writeBundle() {
      const target = join(process.cwd(), 'dist', 'bundle-stats.json');
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, JSON.stringify({ schema_version: 1, chunks: collectedChunks }, null, 2), 'utf8');
    }
  };
}

export default defineConfig({
  plugins: [sveltekit()],
  build: {
    rollupOptions: {
      plugins: [
        emitBundleStats(),
        visualizer({
          filename: 'dist/visualizer-stats.json',
          template: 'raw-data',
          gzipSize: true,
          brotliSize: true
        })
      ]
    }
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  test: {
    environment: 'jsdom',
    include: ['tests/component/**/*.test.{ts,js}'],
    globals: true,
    setupFiles: ['tests/setup.ts']
  }
});
