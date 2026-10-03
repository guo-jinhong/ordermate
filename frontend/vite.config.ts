import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/cart': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/auth': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/chat': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        timeout: 310_000,
        proxyTimeout: 310_000,
      },
      '/operations': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/confirm': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/conversation': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    exclude: ['tests/**', 'e2e/**', 'node_modules/**', 'dist/**'],
  },
})
