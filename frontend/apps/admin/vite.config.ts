import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

export default defineConfig({
  plugins: [react()],
  
  server: {
    port: 5173,
    strictPort: false,
    host: true,
  },
  
  resolve: {
    alias: {
      './runtimeConfig': './runtimeConfig.browser',
      '@shared': resolve(__dirname, '../../shared'),
    },
  },
  
  define: {
    global: 'globalThis',
  },
  
  optimizeDeps: {
    esbuildOptions: {
      define: {
        global: 'globalThis',
      },
    },
  },
  
  build: {
    outDir: '../../dist/admin',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
        },
      },
    },
  },
});