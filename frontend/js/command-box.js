/* ============================================================================
   VECTOR · command-box.js — Persistent command bar for phone/remote control.
   Sits at the bottom of the HUD so it's accessible without a keyboard shortcut.
   Routes through V.command() → CFG.base/command; when the HUD is opened via
   the cloud brain URL that's the Fly queue → laptop drains it every ~3s.
   ========================================================================== */
(function (global) {
  'use strict';

  // Only inject when VECTOR core is available.
  const V = global.VECTOR;
  if (!V) return;

  // ── Build the DOM ──────────────────────────────────────────────────────────
  const bar = document.createElement('div');
  bar.id = 'cmd-bar';
  bar.innerHTML =
    '<input id="cmd-bar-input" type="text" autocomplete="off" spellcheck="false"' +
    ' placeholder="tell VECTOR…" maxlength="500" />' +
    '<button id="cmd-bar-send" aria-label="Send">▶</button>' +
    '<div id="cmd-bar-toast"></div>';
  document.getElementById('stage').appendChild(bar);

  const input  = document.getElementById('cmd-bar-input');
  const btn    = document.getElementById('cmd-bar-send');
  const toast  = document.getElementById('cmd-bar-toast');

  let _toastTimer = null;
  function showToast(msg, ok) {
    clearTimeout(_toastTimer);
    toast.textContent = msg;
    toast.className = ok ? 'ok' : 'err';
    toast.style.opacity = '1';
    _toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 3200);
  }

  async function send() {
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    btn.disabled = true;
    showToast('sending…', true);
    try {
      const r = await V.command(text, 'normal');
      // Cloud brain returns { ok, command_id, queued }; local API returns { status, … }
      if (r && (r.ok || r.status === 'queued' || r.command_id)) {
        showToast(r.command_id ? '↑ queued · ' + r.command_id.slice(0, 8) : '✓ sent', true);
      } else {
        showToast(r && r.detail ? r.detail : '✓ sent', true);
      }
    } catch (e) {
      showToast('✕ ' + String(e).slice(0, 60), false);
    } finally {
      btn.disabled = false;
    }
  }

  btn.addEventListener('click', send);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    e.stopPropagation(); // don't fire global HUD hotkeys while typing
  });

  // ── CSS (injected inline so the module is self-contained) ─────────────────
  const style = document.createElement('style');
  style.textContent = `
#cmd-bar {
  position: fixed;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(0,8,24,.82);
  border: 1px solid rgba(0,204,255,.22);
  border-radius: 6px;
  padding: 6px 8px;
  backdrop-filter: blur(8px);
  z-index: 9900;
  width: min(560px, calc(100vw - 24px));
  box-shadow: 0 0 16px rgba(0,204,255,.08);
}
#cmd-bar-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: #b0e8ff;
  font: 13px/1.4 'JetBrains Mono', 'Courier New', monospace;
  letter-spacing: .04em;
  caret-color: #00ccff;
}
#cmd-bar-input::placeholder { color: rgba(0,180,255,.35); }
#cmd-bar-send {
  background: none;
  border: 1px solid rgba(0,204,255,.35);
  border-radius: 4px;
  color: #00ccff;
  font-size: 12px;
  padding: 3px 9px;
  cursor: pointer;
  transition: background .15s;
  touch-action: manipulation;
}
#cmd-bar-send:hover:not(:disabled) { background: rgba(0,204,255,.12); }
#cmd-bar-send:disabled { opacity: .4; cursor: default; }
#cmd-bar-toast {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  right: 0;
  text-align: center;
  font: 11px 'JetBrains Mono', monospace;
  pointer-events: none;
  transition: opacity .4s;
  opacity: 0;
}
#cmd-bar-toast.ok  { color: #00cc88; }
#cmd-bar-toast.err { color: #ff4466; }
@media (max-width: 480px) {
  #cmd-bar { bottom: 8px; padding: 8px 10px; }
  #cmd-bar-input { font-size: 15px; }
  #cmd-bar-send  { padding: 5px 13px; font-size: 14px; }
}`;
  document.head.appendChild(style);

  global.VectorCommandBox = { focus: () => input.focus() };
})(window);
