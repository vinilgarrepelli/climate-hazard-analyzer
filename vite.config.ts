import { defineConfig } from 'vite';

export default defineConfig({
  root: 'frontend',
  publicDir: 'static',
  build: { outDir: '../public', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
