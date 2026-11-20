import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { avatarkitVitePlugin } from '@spatius/avatarkit/vite';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), avatarkitVitePlugin()],
  // In the monorepo the Vite root is apps/web; this keeps `npm run dev` from
  // root and from apps/web both working.
  root: __dirname,
  publicDir: path.resolve(__dirname, 'public'),
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    proxy: { '/api': 'http://127.0.0.1:3001' },
  },
  build: {
    // In monorepo, output is apps/web/dist; apps/api also checks repo/dist for legacy
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
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
