/* ============================================================================
   VECTOR · config.js  —  FRONTEND runtime config (loaded by the browser).
   This is NOT backend code. FastAPI just serves it as a static file next to
   index.html. Edit the values here (or inject them at deploy time) to point
   the HUD at your backend.

   ⚠ Do NOT commit a real API key to a public repo. For production, leave
   apiKey empty here and have your server inject it, or pass it via the URL:
       VECTOR.html?base=http://127.0.0.1:8000&key=YOUR_KEY
   ========================================================================== */
window.VECTOR_CONFIG = {
  // Backend base URL (FastAPI). Empty string = run on built-in demo data.
  base: 'http://127.0.0.1:8000',

  // Optional WebSocket base. Leave blank to derive from `base` (http→ws).
  ws: '',

  // Bearer token (VECTOR_API_KEY). Leave '' for localhost-only / no-auth.
  apiKey: '',

  // Set false to ignore everything above and force offline demo mode.
  autoConnect: true
};

// Compatibility alias for older widgets that read VECTOR_CFG.api.
window.VECTOR_CFG = window.VECTOR_CFG || {};
Object.defineProperty(window.VECTOR_CFG, 'api', {
  configurable: true,
  get() {
    return (window.VECTOR && window.VECTOR.config && window.VECTOR.config.base)
      || window.VECTOR_CONFIG.base
      || '';
  }
});
Object.defineProperty(window.VECTOR_CFG, 'ws', {
  configurable: true,
  get() {
    return (window.VECTOR && window.VECTOR.config && window.VECTOR.config.ws)
      || window.VECTOR_CONFIG.ws
      || '';
  }
});
