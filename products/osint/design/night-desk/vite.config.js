import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    host: true,
    // Forward /api/* to our own data-source proxy (server/proxy.mjs), which holds
    // secret keys server-side. Keeps secrets out of the browser bundle.
    proxy: { '/api': { target: 'http://localhost:8788', changeOrigin: true } },
  },
});
