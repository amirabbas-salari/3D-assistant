// LEGACY SHIM — canonical: apps/web/vite.config.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { avatarkitVitePlugin } from '@spatius/avatarkit/vite';

export default defineConfig({
  plugins: [react(), avatarkitVitePlugin()],
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: { '/api': 'http://127.0.0.1:3001' },
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/livekit-client/')) return 'livekit';
        },
      },
    },
  },
});
