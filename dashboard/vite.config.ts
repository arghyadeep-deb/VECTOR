import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 7789,
    strictPort: true,
    proxy: {
      // Proxy WebSocket to VECTOR core
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
