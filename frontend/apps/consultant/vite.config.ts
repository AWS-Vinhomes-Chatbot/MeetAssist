import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@shared': resolve(__dirname, '../../shared'),
    },
  },
  server: {
    port: 5174,  // Different port from admin (5173)
    host: true
  },
  build: {
    outDir: '../../dist/consultant',
    emptyOutDir: true,
    sourcemap: true
  }
})
