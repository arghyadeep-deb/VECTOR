/* ============================================================================
   VECTOR · hud-controls.js — the labelled HUD controls (VOICE, CHAT, GOALS, APPROVALS, PANELS, SOUND), each with a
   text label so nothing is a mystery icon. The vision/gesture buttons live in the subsystem dock (demo.js), which
   needs the MediaPipe vendor scripts VECTOR.html loads.
   Power panels (code graph, mission control, …) stay reachable via the
   Ctrl+Shift+H terminal ("ls" lists them) — not as dock clutter.
   ========================================================================== */
(function (global) {
  const V = global.VECTOR;
  if (!V) return;

  const icons = {
    mic:'<path d="M8 2a2 2 0 0 0-2 2v4a2 2 0 0 0 4 0V4a2 2 0 0 0-2-2z"/><path d="M4 7v1a4 4 0 0 0 8 0V7"/><path d="M8 12v2M5.5 14h5"/>',
    chat:'<path d="M2 3h12v8H7l-4 3v-3H2z"/>',
    goals:'<path d="M8 2l5 3v6l-5 3-5-3V5z"/><path d="M8 5v6M5 8h6"/>',
    approvals:'<path d="M8 2l5 2v5c0 3-2.5 4.5-5 5-2.5-.5-5-2-5-5V4z"/><path d="M5.5 8l2 2 3-3.5"/>',
    screen:'<rect x="2" y="3" width="12" height="8" rx="1"/><path d="M6 14h4M8 11v3"/>',
    sound:'<path d="M2 6h3l4-3v10L5 10H2z"/><path d="M11 5a4 4 0 0 1 0 6M13 3a7 7 0 0 1 0 10"/>'
  };
  const svg = key => `<svg viewBox="0 0 16 16">${icons[key] || icons.screen}</svg>`;

  function setOn(key, on) {
    const b = document.querySelector(`#dock .d-btn[data-key="${key}"]`);
    if (b) b.classList.toggle('on', !!on);
  }

  function flash(msg, ms) {
    V.caption(msg);
    clearTimeout(flash._t);
    flash._t = setTimeout(() => V.caption(''), ms || 3000);
  }

  async function toggleVoice() {
    // Preflight the mic so failures are VISIBLE with a fix, never silent.
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      flash('Mic needs HTTPS or localhost — open the HUD on the laptop (localhost) for voice.', 6000);
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach(t => t.stop());
    } catch (e) {
      flash('Microphone blocked — click the padlock icon in the address bar → allow Microphone → reload.', 7000);
      return;
    }
    // One voice engine, clear on/off: duplex (server Whisper) first, browser SR fallback.
    const D = global.VectorVoiceDuplex;
    if (D) {
      if (D.active) { D.stop(); setOn('mic', false); flash('Voice off.', 1500); }
      else {
        await D.start();
        setOn('mic', true);
        flash('Voice on — just speak.', 2500);
      }
      return;
    }
    if (global.VectorSpeech) { setOn('mic', global.VectorSpeech.toggle()); }
  }

  function toggleSound() {
    if (!global.VectorAudio) return;
    const on = !global.VectorAudio.enabled;
    global.VectorAudio.setEnabled(on);
    setOn('sound', on);
  }

  function buildDock() {
    const dock = document.getElementById('dock');
    if (!dock || dock.dataset.controls === 'ready') return;
    dock.dataset.controls = 'ready';
    dock.innerHTML = '';

    const items = [
      ['mic',       'VOICE',     toggleVoice],
      ['chat',      'CHAT',      () => V.openWidget('chat')],
      ['goals',     'GOALS',     () => V.openWidget('goals')],
      ['approvals', 'APPROVALS', () => V.openWidget('approvals')],
      ['screen',    'PANELS',    () => {
        // Opening the workspace with nothing in it is a dead end (76_HUD_VISUAL_AUDIT.md
        // F5) — the Command Center is the discovery layer, so surface it here instead of
        // an empty canvas. Only when truly nothing is open; toggling closed, or reopening
        // a workspace that already has panels in it, behaves exactly as before.
        if (!V.isWorkspaceOpen && document.querySelectorAll('#workspace .widget').length === 0) {
          V.openWidget('commandcenter');
        } else {
          V.toggleWorkspace();
        }
      }],
      ['sound',     'SOUND',     toggleSound, null, true]
    ];

    items.forEach(item => {
      const key = item[3] || item[0];
      const b = document.createElement('button');
      b.className = 'd-btn';
      b.type = 'button';
      b.dataset.key = key;
      b.title = item[1];
      b.setAttribute('aria-label', item[1]);
      b.innerHTML = svg(item[0]) + `<span class="d-lbl">${item[1]}</span>`;
      if (item[4]) b.classList.add('on');
      b.addEventListener('click', e => {
        e.stopPropagation();
        item[2]();
      });
      dock.appendChild(b);
    });

    V.on('state', ({to}) => setOn('mic',
      (global.VectorVoiceDuplex && global.VectorVoiceDuplex.active) ||
      (global.VectorSpeech && global.VectorSpeech.active) || to === 'listening'));
    V.on('workspace', ({open}) => setOn('screen', open));
  }

  if (document.readyState !== 'loading') buildDock();
  else addEventListener('DOMContentLoaded', buildDock);

  global.VectorHudControls = { buildDock };
})(window);
