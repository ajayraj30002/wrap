import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/analytics': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/healthz': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/ready': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/metrics': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/docs': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      },
      '/openapi.json': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
})
