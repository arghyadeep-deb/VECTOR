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
      // ── WebSocket endpoints ──────────────────────────────────────────────
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true },
      '/gesture/ws': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true },
      '/camera/ws': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true },
      '/ws/voice/stream': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true },

      // ── New JARVIS REST endpoints ────────────────────────────────────────
      '/sb': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/finance': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/news': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/location': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/voice': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/nudge': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/vectorcode': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/claims': { target: 'http://127.0.0.1:8000', changeOrigin: true },

      // ── Existing REST endpoints ──────────────────────────────────────────
      '^/(csrf-token|status|system|daily|memory|agents|agent|command|council|security|tasks|loop|scheduler|inference|email|channels|providers|tools|network|audit|metering|jupyter|sandbox|sensing|media|mining|mcp|video|scraper|seo|oauth|research|migration|api)(/.*)?$': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
