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
      '^/(api|status|ui|ws|vectorcode|agent|agents|command|csrf-token|system|daily|memory|council)(/.*)?$': {
        target: 'https://127.0.0.1:8001',
        secure: false,
      },
    },
  },
})
