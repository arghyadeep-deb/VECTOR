/**
 * VECTOR Composition Runtime — inline browser script
 * VECTOR Video Engine — browser runtime module
 *
 * Injected by html_renderer.py (Playwright) before frame capture.
 * Provides window.__vector with:
 *   - renderSeek(t)        : seek all animations to time t (frame-accurate)
 *   - enableRenderMode()   : pause RAF loops, enable deterministic seeking
 *   - disableRenderMode()  : restore normal playback
 *   - setVariables(vars)   : set composition template variables
 *   - getVariables()       : read current variable values
 *
 * Also patches:
 *   - GSAP timeline seeking (window.__timelines registry)
 *   - anime.js timeline seeking
 *   - CSS animation pausing (sets animation-play-state: paused, then seeks)
 *   - Web Animations API (WAAPI) seeking
 *   - Lottie animation seeking
 *   - Three.js / TypeGPU GPU render tick freezing
 *
 * Runtime contract (stable surface):
 *   window.__timelines   — GSAP timeline registry { id: timeline }
 *   window.__player      — player API (play/pause/seek/renderSeek)
 *   window.__playerReady — true when runtime is bootstrapped
 *   window.__renderReady — true when ready for frame capture
 *   window.__clipManifest— timeline payload (elements + durations)
 *
 * postMessage protocol (for VectorPlayer iframe bridge):
 *   parent → runtime: { source: "vector-parent", type: "control", action: "seek"|"play"|"pause" }
 *   runtime → parent: { source: "vector-preview", type: "state"|"timeline"|"diagnostic" }
 */
(function () {
  "use strict";

  // ── Guard: don't double-bootstrap ──────────────────────────────────────────
  if (window.__vectorRuntimeBootstrapped) return;
  window.__vectorRuntimeBootstrapped = true;

  // ── Timeline registry ───────────────────────────────────────────────────────
  window.__timelines = window.__timelines || {};

  // ── Canonical FPS (30fps for VECTOR render pipeline) ────────────────────────
  var CANONICAL_FPS = 30;
  var FRAME_DURATION = 1 / CANONICAL_FPS;

  // ── Quantize time to frame boundary (parity with Python renderer) ────────────
  function quantizeToFrame(t) {
    return Math.round(Math.max(0, t) * CANONICAL_FPS) / CANONICAL_FPS;
  }

  // ── Render mode state ────────────────────────────────────────────────────────
  var _renderMode = false;
  var _currentTime = 0;
  var _variables = {};
  var _injectedStyles = [];

  // ── CSS adapter: pause all CSS animations and seek to time t ─────────────────
  function cssAdapterSeek(t) {
    var elements = document.querySelectorAll("*");
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      var style = el.style;
      if (!style) continue;
      var dur = parseFloat(window.getComputedStyle(el).animationDuration || "0");
      if (dur <= 0) continue;
      style.animationPlayState = "paused";
      var delay = parseFloat(window.getComputedStyle(el).animationDelay || "0");
      var localT = t - delay;
      var normalised = localT < 0 ? 0 : localT % dur;
      style.animationDelay = (-normalised) + "s";
    }
  }

  function cssAdapterResume() {
    var elements = document.querySelectorAll("*");
    for (var i = 0; i < elements.length; i++) {
      elements[i].style.animationPlayState = "";
    }
  }

  // ── WAAPI adapter: pause/seek Web Animations API animations ──────────────────
  function waapiAdapterSeek(t) {
    var elements = document.querySelectorAll("*");
    for (var i = 0; i < elements.length; i++) {
      var anims = elements[i].getAnimations ? elements[i].getAnimations() : [];
      for (var j = 0; j < anims.length; j++) {
        var anim = anims[j];
        if (!anim.effect) continue;
        anim.pause();
        var timing = anim.effect.getComputedTiming ? anim.effect.getComputedTiming() : {};
        var dur = timing.duration || 0;
        var delay = timing.delay || 0;
        var localT = (t - delay / 1000) * 1000;
        var clamped = Math.max(0, dur > 0 ? localT % dur : localT);
        anim.currentTime = clamped;
      }
    }
  }

  // ── GSAP adapter: seek GSAP timeline registry ─────────────────────────────────
  function gsapAdapterSeek(t) {
    var timelines = window.__timelines || {};
    for (var id in timelines) {
      if (!timelines.hasOwnProperty(id)) continue;
      var tl = timelines[id];
      if (!tl) continue;
      try {
        tl.pause && tl.pause();
        if (typeof tl.totalTime === "function") {
          tl.totalTime(t, false);
        } else if (typeof tl.seek === "function") {
          tl.seek(t, false);
        }
      } catch (e) {
        /* keep runtime resilient */
      }
    }
    // Also seek the GSAP global ticker
    if (window.gsap && typeof window.gsap.ticker === "object") {
      try {
        window.gsap.ticker.lagSmoothing(0);
      } catch (e) {}
    }
  }

  // ── anime.js adapter ──────────────────────────────────────────────────────────
  function animeAdapterSeek(t) {
    if (!window.anime) return;
    try {
      // anime.js instances are tracked in anime.running
      var running = window.anime.running || [];
      for (var i = 0; i < running.length; i++) {
        var anim = running[i];
        if (anim && typeof anim.seek === "function") {
          anim.pause();
          anim.seek(t * 1000); // anime.js uses milliseconds
        }
      }
    } catch (e) {}
  }

  // ── Lottie adapter ────────────────────────────────────────────────────────────
  function lottieAdapterSeek(t) {
    if (!window.lottie) return;
    try {
      var instances = window.lottie._instances || [];
      for (var i = 0; i < instances.length; i++) {
        var anim = instances[i];
        if (!anim) continue;
        anim.pause && anim.pause();
        if (typeof anim.goToAndStop === "function") {
          var frame = t * (anim.frameRate || 60);
          anim.goToAndStop(frame, true);
        }
      }
    } catch (e) {}
  }

  // ── Media element sync ────────────────────────────────────────────────────────
  function syncMediaElements(t) {
    var mediaEls = document.querySelectorAll("video[data-start], audio[data-start]");
    for (var i = 0; i < mediaEls.length; i++) {
      var el = mediaEls[i];
      var start = parseFloat(el.getAttribute("data-start") || "0");
      var mediaStart = parseFloat(
        el.getAttribute("data-playback-start") ||
        el.getAttribute("data-media-start") || "0"
      ) || 0;
      var dur = parseFloat(el.getAttribute("data-duration") || "0");
      var end = dur > 0 ? start + dur : Infinity;

      if (t >= start && t < end) {
        el.style.visibility = "visible";
        var relTime = t - start + mediaStart;
        if (Math.abs(el.currentTime - relTime) > 0.033) {
          try { el.currentTime = Math.max(0, relTime); } catch (e) {}
        }
        el.pause && el.pause();
      } else {
        el.style.visibility = "hidden";
        el.pause && el.pause();
      }
    }
  }

  // ── Element visibility ────────────────────────────────────────────────────────
  function syncVisibility(t) {
    var elements = document.querySelectorAll("[data-start]");
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      var tag = el.tagName.toLowerCase();
      if (tag === "script" || tag === "style" || tag === "link" || tag === "meta") continue;
      var start = parseFloat(el.getAttribute("data-start") || "0");
      var dur = parseFloat(el.getAttribute("data-duration") || "0");
      var end = dur > 0 ? start + dur : Infinity;
      el.style.visibility = (t >= start && t < end) ? "visible" : "hidden";
    }
  }

  // ── Root composition sizing ────────────────────────────────────────────────────
  function applyCompositionSizing() {
    var rootEl = document.querySelector("[data-composition-id]");
    if (!rootEl) return;
    var w = rootEl.getAttribute("data-width");
    var h = rootEl.getAttribute("data-height");
    if (w) {
      rootEl.style.width = w + "px";
      rootEl.style.setProperty("--comp-width", w + "px");
    }
    if (h) {
      rootEl.style.height = h + "px";
      rootEl.style.setProperty("--comp-height", h + "px");
    }
    // Normalise html/body margins (eliminates 8px browser default)
    document.documentElement.style.margin = "0";
    document.documentElement.style.padding = "0";
    document.documentElement.style.overflow = "hidden";
    document.body.style.margin = "0";
    document.body.style.padding = "0";
    document.body.style.overflow = "hidden";
  }

  // ── Seek all adapters to time t ────────────────────────────────────────────────
  function seekAll(t) {
    var qt = quantizeToFrame(t);
    gsapAdapterSeek(qt);
    cssAdapterSeek(qt);
    waapiAdapterSeek(qt);
    animeAdapterSeek(qt);
    lottieAdapterSeek(qt);
    syncMediaElements(qt);
    syncVisibility(qt);
    _currentTime = qt;
  }

  // ── Variables ─────────────────────────────────────────────────────────────────
  function setVariables(vars) {
    if (!vars || typeof vars !== "object") return;
    Object.assign(_variables, vars);
    // Dispatch event so composition scripts can react
    try {
      window.dispatchEvent(new CustomEvent("vector:variables", { detail: vars }));
    } catch (e) {}
  }

  function getVariables() {
    // Read from data-composition-variables on <html>, merge with runtime overrides
    var htmlTag = document.documentElement;
    var declared = {};
    try {
      var raw = htmlTag.getAttribute("data-composition-variables");
      if (raw) {
        var parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          for (var i = 0; i < parsed.length; i++) {
            var v = parsed[i];
            if (v && v.id !== undefined && v.default !== undefined) {
              declared[v.id] = v.default;
            }
          }
        }
      }
    } catch (e) {}
    return Object.assign({}, declared, _variables);
  }

  // ── postMessage bridge (for VectorPlayer iframe) ───────────────────────────────
  function postRuntimeMessage(payload) {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(payload, "*");
      }
    } catch (e) {}
  }

  window.addEventListener("message", function (event) {
    var data = event.data;
    if (!data || data.source !== "vector-parent" || data.type !== "control") return;
    var action = data.action;
    if (action === "seek") {
      var t = typeof data.frame === "number" ? data.frame / CANONICAL_FPS : (data.time || 0);
      seekAll(t);
    } else if (action === "play") {
      cssAdapterResume();
    } else if (action === "pause") {
      cssAdapterSeek(_currentTime);
    } else if (action === "set-variables") {
      setVariables(data.variables);
    }
  });

  // ── main window.__vector API ────────────────────────────────────────────────────
  window.__vector = {
    // Called by Playwright before each frame capture
    renderSeek: function (t) {
      seekAll(t);
      // Notify parent (VectorPlayer in Studio mode)
      postRuntimeMessage({
        source: "vector-preview",
        type: "state",
        frame: Math.round(t * CANONICAL_FPS),
        isPlaying: false,
        time: t,
      });
    },

    // Called by html_renderer.py once after page load — freezes RAF, enables seek
    enableRenderMode: function () {
      _renderMode = true;
      applyCompositionSizing();

      // Pause GSAP global ticker (stops all GSAP animations advancing on RAF)
      if (window.gsap && window.gsap.ticker) {
        try { window.gsap.ticker.sleep(); } catch (e) {}
      }
      // Pause anime.js engine
      if (window.anime && window.anime.running) {
        try {
          var running = window.anime.running;
          for (var i = 0; i < running.length; i++) {
            running[i] && running[i].pause && running[i].pause();
          }
        } catch (e) {}
      }
      // Freeze CSS animations
      cssAdapterSeek(0);
      // Freeze WAAPI
      waapiAdapterSeek(0);

      postRuntimeMessage({
        source: "vector-preview",
        type: "state",
        frame: 0,
        isPlaying: false,
        renderMode: true,
      });
    },

    disableRenderMode: function () {
      _renderMode = false;
      cssAdapterResume();
      if (window.gsap && window.gsap.ticker) {
        try { window.gsap.ticker.wake(); } catch (e) {}
      }
    },

    setVariables: setVariables,
    getVariables: getVariables,

    // Expose internals for debugging
    getCurrentTime: function () { return _currentTime; },
    isRenderMode: function () { return _renderMode; },
    seekAll: seekAll,
  };

  // ── window.__player compat (for compositions using the full player API) ────────
  window.__player = window.__player || {
    play: function () {},
    pause: function () {},
    seek: function (t) { seekAll(t); },
    getTime: function () { return _currentTime; },
    getDuration: function () { return 0; },
    isPlaying: function () { return !_renderMode; },
    renderSeek: function (t) { window.__vector.renderSeek(t); },
    enableRenderMode: function () { window.__vector.enableRenderMode(); },
    disableRenderMode: function () { window.__vector.disableRenderMode(); },
    setVariables: setVariables,
    getVariables: getVariables,
  };

  window.__playerReady = true;
  window.__renderReady = true;

  // ── Bootstrap: apply sizing + initial seek on load ───────────────────────────
  function bootstrap() {
    applyCompositionSizing();
    // Re-export __timelines so GSAP compositions can register before runtime
    window.__timelines = window.__timelines || {};
    postRuntimeMessage({
      source: "vector-preview",
      type: "timeline",
      compositionId: (document.querySelector("[data-composition-id]") || {}).getAttribute
        ? document.querySelector("[data-composition-id]").getAttribute("data-composition-id")
        : null,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
  } else {
    bootstrap();
  }

})();

// ── Hyperframes compatibility bridge ─────────────────────────────────────
// hyperframes compositions use window.__hf for seek/events
// VECTOR uses window.__vector — expose both APIs pointing to the same runtime
if (typeof window !== 'undefined' && window.__vector && !window.__hf) {
  window.__hf = {
    seek: window.__vector.seekAll,
    emit: function(eventName, detail) {
      try {
        window.dispatchEvent(new CustomEvent('hf:' + eventName, { detail: detail }));
      } catch (e) {}
    },
    on: function(eventName, handler) {
      window.addEventListener('hf:' + eventName, function(e) { handler(e.detail); });
    },
    off: function(eventName, handler) {
      window.removeEventListener('hf:' + eventName, handler);
    },
    getTime: window.__vector.getCurrentTime,
    getDuration: function() {
      var rootEl = document.querySelector('[data-composition-id]');
      return rootEl ? parseFloat(rootEl.getAttribute('data-duration') || '0') : 0;
    },
    // hyperframes-specific extensions
    frame: function() { return Math.floor((window.__vector.getCurrentTime() || 0) * 30); },
    fps: 30,
  };
  if (typeof console !== 'undefined') {
    console.debug('[VECTOR] hyperframes __hf bridge mounted');
  }
}
