import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom'] },
  server: { host: '127.0.0.1', port: 18800, strictPort: true },
  preview: { host: '127.0.0.1', port: 18801, strictPort: true },
  build: { chunkSizeWarningLimit: 900 },
});
