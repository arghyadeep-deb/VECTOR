// VECTOR HUD service worker -- RETIRED (self-removing).
//
// Why this exists: an earlier HUD registered an offline-cache service worker (cache "vector-hud-v1") that stored the old
// "VECTOR Production" page and served it whenever the network failed or lagged -- so after that page was removed
// (2026-09-25) the browser kept showing it, as raw unstyled HTML when the backend was starting or down.
// The one HUD (VECTOR.html) does not register a service worker, so nothing should intercept requests any more.
//
// A browser that still has the old worker re-fetches this file on its next visit to /hud/. On install it takes over at
// once; on activate it deletes every cache, unregisters itself and reloads any open HUD window straight from the network.
// There is deliberately no "fetch" handler: it never answers a request itself.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((key) => caches.delete(key)));
      } catch (_) { /* nothing to clean */ }
      try {
        await self.registration.unregister();
      } catch (_) { /* already gone */ }
      try {
        const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
        windows.forEach((client) => { try { client.navigate(client.url); } catch (_) { /* window closed */ } });
      } catch (_) { /* no clients */ }
    })()
  );
});
