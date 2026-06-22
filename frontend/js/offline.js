/* ============================================================================
   VECTOR offline runtime.
   Registers the HUD service worker only when served over http(s). Static file
   usage stays unchanged and simply runs without an offline cache.
   ========================================================================== */
(function (global) {
  const V = global.VECTOR;
  const canUseServiceWorker =
    "serviceWorker" in navigator &&
    (location.protocol === "http:" || location.protocol === "https:");

  function setOfflineMode(offline) {
    const stage = document.getElementById("stage");
    if (stage) stage.dataset.network = offline ? "offline" : "online";
    if (V && typeof V.emit === "function") {
      V.emit("network", { online: !offline });
    }
  }

  global.addEventListener("online", () => setOfflineMode(false));
  global.addEventListener("offline", () => setOfflineMode(true));
  setOfflineMode(!navigator.onLine);

  if (!canUseServiceWorker) {
    global.VectorOffline = { enabled: false, reason: "unsupported-protocol" };
    return;
  }

  const scriptUrl = new URL("sw.js", location.href);
  navigator.serviceWorker.register(scriptUrl.href, { scope: "./" })
    .then(registration => {
      global.VectorOffline = { enabled: true, registration };
      console.info("[VECTOR] offline cache ready");
    })
    .catch(error => {
      global.VectorOffline = { enabled: false, error };
      console.warn("[VECTOR] offline cache unavailable", error);
    });
})(window);
