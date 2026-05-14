import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/status': 'http://127.0.0.1:8000',
      '/ui': 'http://127.0.0.1:8000',
      '/ws': 'http://127.0.0.1:8000',
    },
  },
})
