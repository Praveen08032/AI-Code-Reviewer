import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  server: {
    proxy: { '/auth': { target: 'http://127.0.0.1:9055', changeOrigin: false } },
    headers: { 'Cross-Origin-Opener-Policy': 'same-origin-allow-popups' },
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
});
