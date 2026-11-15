/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, las peticiones /api se reenvían al backend FastAPI (puerto 8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
  test: { environment: 'node', include: ['src/**/*.test.{ts,tsx}'] },
})
