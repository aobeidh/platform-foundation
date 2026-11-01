import path from 'node:path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

// `vite` serves the portal and proxies /api to a running service (API_URL, default the exemplar on :8000).
// `vite build --mode single` makes one self-contained HTML file that runs on the simulated API provider.
export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), ...(mode === 'single' ? [viteSingleFile()] : [])],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  define: { __API_MODE__: JSON.stringify(mode === 'single' ? 'simulated' : process.env.API_MODE ?? 'auto') },
  server: { proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000', '/health': process.env.API_URL ?? 'http://localhost:8000' } },
  build: mode === 'single'
    ? { outDir: 'dist-single', assetsInlineLimit: 100_000_000, cssCodeSplit: false, chunkSizeWarningLimit: 5000 }
    : { outDir: 'dist', chunkSizeWarningLimit: 1500 },
}));
