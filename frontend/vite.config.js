import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Port is fixed because the FastAPI CORS list only allows :5173.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: '127.0.0.1', strictPort: true },
  build: {
    chunkSizeWarningLimit: 1600,
    rollupOptions: { output: { manualChunks: { plotly: ['plotly.js-basic-dist-min'] } } }
  }
});
