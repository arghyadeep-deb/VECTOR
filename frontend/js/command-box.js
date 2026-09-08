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
  bar.setAttribute('role', 'region');
  bar.setAttribute('aria-label', 'Command bar');
  bar.innerHTML =
    '<input id="cmd-bar-input" type="text" autocomplete="off" spellcheck="false"' +
    ' placeholder="tell VECTOR…" maxlength="500" aria-label="Tell VECTOR" />' +
    '<button id="cmd-bar-send" aria-label="Send">▶</button>' +
    '<div id="cmd-bar-toast" role="status" aria-live="polite"></div>';
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

  // Generation counter: every send() gets the next value. A response is only
  // allowed to touch the UI while its own value still matches `seq` — i.e.
  // while it's still the most recent command in flight. This is what lets a
  // late answer be shown (instead of silently discarded, the old bug) while
  // also guaranteeing a *stale* late answer from an earlier command can never
  // overwrite — or be mistaken for — the reply to a command sent after it.
  let seq = 0;

  async function send() {
    const text = input.value.trim();
    if (!text) return;

    // Local panel routing (2026-07-19 browser dogfood): "open telemetry" typed
    // here went to the backend LLM, which hallucinated an OpenTelemetry SDK
    // tutorial instead of opening the panel. Panel verbs are HUD commands, not
    // questions — route them to the widget system before touching the LLM.
    const mPanel = text.toLowerCase().match(/^(open|show|close|hide)\s+([a-z0-9_]+)$/);
    if (mPanel) {
      const ids = (window.VectorTerminal && window.VectorTerminal.WIDGETS) || [];
      const id = mPanel[2];
      if (ids.includes(id)) {
        input.value = '';
        if (mPanel[1] === 'close' || mPanel[1] === 'hide') { V.closeWidget(id); showToast('✓ closed ' + id, true); }
        else { V.openWidget(id); showToast('✓ opened ' + id, true); }
        return;
      }
    }

    input.value = '';
    const mySeq = ++seq;
    btn.disabled = true;
    showToast('processing…', true);

    // Client-side "still working" notice at 35s — the brain's heavy compute
    // can stall the HTTP response for a long time (server-side cap is 120s;
    // real p99 latencies reach ~105s), and the bar shouldn't look frozen on
    // "processing…" the whole time — matches the orb's own PROCESSING state
    // label (vector-core.js) rather than an invented cognitive term. Unlike
    // the old Promise.race version, this
    // does NOT cancel or stop listening to the real request — it only
    // updates the toast and re-enables the button so the user can fire off
    // another command while this one keeps working in the background.
    // A second, longer backstop covers the (rare) case where the request
    // never settles at all, so the bar never gets stuck silently forever.
    let settled = false;
    let wasSlow = false;
    const softTimer = setTimeout(() => {
      if (settled || mySeq !== seq) return; // already done, or superseded by a newer command
      wasSlow = true;
      showToast('VECTOR is busy — still working, try again in a moment', false);
      btn.disabled = false;
    }, 35000);
    const hardTimer = setTimeout(() => {
      if (settled || mySeq !== seq) return;
      showToast('✕ still no response — the request may have failed', false);
    }, 150000); // 120s server cap + margin; purely informational, request keeps listening past this too

    try {
      const r = await V.command(text, 'normal');
      settled = true;
      clearTimeout(softTimer); clearTimeout(hardTimer);
      if (mySeq !== seq) return; // a newer command now owns the bar — don't show this as its reply

      if (r && r.command_id) {
        showToast('↑ queued · ' + r.command_id.slice(0, 8), true);
      } else if (r && (r.response || r.text || r.result)) {
        // Show VECTOR's ACTUAL answer (was discarded before — you'd ask a
        // question and never see the reply). Speaks + captions it, marked
        // as delayed if it arrived after the "still working" notice fired.
        const answer = String(r.response || r.text || r.result);
        showToast(wasSlow ? '✓ delayed reply' : '✓ done', true);
        const spoken = wasSlow ? '(delayed reply) ' + answer : answer;
        if (V.say) V.say(spoken); else if (V.caption) V.caption(spoken);
      } else if (r && (r.ok || r.status === 'queued')) {
        showToast('✓ sent', true);
      } else {
        showToast(r && r.detail ? r.detail : '✓ sent', true);
      }
    } catch (e) {
      settled = true;
      clearTimeout(softTimer); clearTimeout(hardTimer);
      if (mySeq !== seq) return; // stale failure for a superseded command — nothing to show
      showToast(('✕ ' + String((e && e.message) || e)).slice(0, 70), false);
    } finally {
      if (mySeq === seq) btn.disabled = false;
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
  bottom: 74px; /* clear of .ticker.bot (40-66px) — mobile override below */
  left: 50%;
  transform: translateX(-50%);
  /* hidden until the HUD wakes — no controls before the stage is live */
  opacity: 0;
  pointer-events: none;
  transition: opacity .5s;
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
  font-size: 13px;
  padding: 8px 14px;
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
#stage.awake #cmd-bar { opacity: 1; pointer-events: auto; }
@media (max-width: 640px) {
  #cmd-bar { bottom: 8px; padding: 10px 12px; } /* .ticker.bot is hidden on mobile */
  #cmd-bar-input { font-size: 16px; } /* 16px stops mobile auto-zoom-on-focus */
  #cmd-bar-send  { padding: 10px 18px; font-size: 15px; min-height: 42px; }
}`;
  document.head.appendChild(style);

  global.VectorCommandBox = { focus: () => input.focus() };
})(window);
