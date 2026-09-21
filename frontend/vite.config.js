import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The browser talks to one origin. The dev server (port 5173) and the preview server (port 4173)
// forward /api to the RAVEN backend on port 8000, so the session cookie stays same-origin.
const backend = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: backend },
  preview: { port: 4173, strictPort: true, proxy: backend },
  build: { sourcemap: false },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
    // Slower machines render the whole app in the first test of a file; give them room.
    testTimeout: 20000,
    hookTimeout: 20000,
    restoreMocks: true,
    unstubEnvs: true,
  },
});
