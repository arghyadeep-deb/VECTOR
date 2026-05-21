import '@testing-library/jest-dom/vitest'

// Stub WebSocket so components that auto-connect (GestureOverlay, voice_ws, etc.) do not throw in jsdom.
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  readyState = MockWebSocket.CONNECTING
  onopen: ((e: Event) => void) | null = null
  onclose: ((e: CloseEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  url: string
  constructor(url: string) { this.url = url }
  send(_: string) { /* no-op */ }
  close() { this.readyState = MockWebSocket.CLOSED }
  addEventListener() {}
  removeEventListener() {}
}
;(globalThis as any).WebSocket = MockWebSocket

// jsdom does not implement matchMedia
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    value: (q: string) => ({
      matches: false,
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      onchange: null,
      dispatchEvent: () => false,
    }),
  })
}

// Mock fetch by default; tests can override.
if (!globalThis.fetch) {
  globalThis.fetch = (() => Promise.resolve(new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }))) as any
}
