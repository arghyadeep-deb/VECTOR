/* ============================================================================
   VECTOR · canvas-pan.js — the workspace is a navigable space, not a fixed
   frame. Drag any EMPTY area to pan the whole panel field in any direction
   (finger or mouse); double-click / double-tap empty space to snap home.

   Gestures land on #canvas-backdrop — a huge invisible layer INSIDE the
   workspace, so it (a) travels with the pan and is always under the pointer,
   and (b) is a SIBLING of the panels, so touch-action:none on it never blocks
   finger-scrolling inside a panel body. Panels keep their own w-head drag.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR; if (!V) return;
  const ws = document.getElementById('workspace'); if (!ws) return;

  const pad = document.createElement('div');
  pad.id = 'canvas-backdrop';
  ws.insertBefore(pad, ws.firstChild);

  let px = 0, py = 0;      // committed pan offset
  let drag = null;         // active pan gesture
  let lastTap = 0;         // double-tap detection (touch has no dblclick)

  function limit() { return { x: innerWidth * 1.2, y: innerHeight * 1.2 }; }
  function apply() {
    ws.style.setProperty('--pan-x', px + 'px');
    ws.style.setProperty('--pan-y', py + 'px');
  }
  function reset() { px = 0; py = 0; apply(); }

  pad.addEventListener('pointerdown', e => {
    const now = Date.now();
    if (now - lastTap < 320) { lastTap = 0; reset(); return; }  // double-tap → home
    lastTap = now;
    drag = { sx: e.clientX, sy: e.clientY, bx: px, by: py, id: e.pointerId };
    ws.classList.add('panning');
    try { pad.setPointerCapture(e.pointerId); } catch (_) {}
  });
  pad.addEventListener('pointermove', e => {
    if (!drag || e.pointerId !== drag.id) return;
    const L = limit();
    px = Math.max(-L.x, Math.min(L.x, drag.bx + (e.clientX - drag.sx)));
    py = Math.max(-L.y, Math.min(L.y, drag.by + (e.clientY - drag.sy)));
    apply();
  });
  function end(e) {
    if (drag && e.pointerId === drag.id) { drag = null; ws.classList.remove('panning'); }
  }
  pad.addEventListener('pointerup', end);
  pad.addEventListener('pointercancel', end);
  pad.addEventListener('dblclick', () => reset());

  // A newly opened panel must be visible — snap home so it never spawns
  // outside the currently panned view.
  V.on('widget:open', () => { if (px || py) reset(); });

  global.VectorCanvas = { reset, get offset() { return { x: px, y: py }; } };
})(window);
