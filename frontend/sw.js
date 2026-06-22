const CACHE_NAME = "vector-hud-v1";

const CORE_ASSETS = [
  "./",
  "VECTOR.prod.html",
  "styles/core.css",
  "styles/widgets.css",
  "dist/vector-hud.prod.js",
  "dist/manifest.json",
  "js/config.js",
];

const CACHEABLE_PATHS = new Set(CORE_ASSETS.map(asset => new URL(asset, self.location.href).pathname));

function shouldCache(request) {
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  if (CACHEABLE_PATHS.has(url.pathname)) return true;
  return url.pathname.startsWith("/styles/")
    || url.pathname.startsWith("/dist/")
    || url.pathname.startsWith("/js/");
}

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  if (!shouldCache(request)) return;

  event.respondWith(
    fetch(request)
      .then(response => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then(cached => {
        if (cached) return cached;
        if (request.mode === "navigate") return caches.match("./");
        return Response.error();
      }))
  );
});
