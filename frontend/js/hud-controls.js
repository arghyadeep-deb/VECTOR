/* ============================================================================
   VECTOR · hud-controls.js — production-safe visible HUD controls.
   No dev panel, no backend credential form, no scripted demo.
   ========================================================================== */
(function (global) {
  const V = global.VECTOR;
  if (!V) return;

  const icons = {
    mic:'<path d="M8 2a2 2 0 0 0-2 2v4a2 2 0 0 0 4 0V4a2 2 0 0 0-2-2z"/><path d="M4 7v1a4 4 0 0 0 8 0V7"/><path d="M8 12v2M5.5 14h5"/>',
    screen:'<rect x="2" y="3" width="12" height="8" rx="1"/><path d="M6 14h4M8 11v3"/>',
    cam:'<path d="M3 5h6l2-2v10l-2-2H3z"/>',
    grid:'<path d="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z"/>',
    music:'<path d="M6 12a2 2 0 1 1-1-1.7V3l7-1v8.8a2 2 0 1 1-1-1.7V5L6 6z"/>',
    vstudio:'<path d="M8 2v12M5 5v6M11 5v6M2 7v2M14 7v2"/>',
    codegraph:'<circle cx="4" cy="4" r="2"/><circle cx="12" cy="4" r="2"/><circle cx="8" cy="12" r="2"/><path d="M6 5l2 5M10 5l-2 5M6 4h4"/>',
    answerengine:'<path d="M3 12l3-3M5 3a5 5 0 1 0 0 10 5 5 0 0 0 0-10z"/><path d="M10 10l4 4"/>',
    goalplanner:'<path d="M8 2l5 3v6l-5 3-5-3V5z"/><path d="M8 5v6M5 8h6"/>',
    hand:'<path d="M5 8V3a1 1 0 0 1 2 0v4M7 7V2a1 1 0 0 1 2 0v5M9 7V3a1 1 0 0 1 2 0v6"/><path d="M5 8l-1-1a1 1 0 0 0-1.5 1.3L5 13h5a3 3 0 0 0 3-3V7"/>',
    sound:'<path d="M2 6h3l4-3v10L5 10H2z"/><path d="M11 5a4 4 0 0 1 0 6M13 3a7 7 0 0 1 0 10"/>',
    features:'<rect x="2" y="2" width="5" height="5"/><rect x="9" y="2" width="5" height="5"/><rect x="2" y="9" width="5" height="5"/><rect x="9" y="9" width="5" height="5"/><path d="M7 4.5h2M7 11.5h2M4.5 7v2M11.5 7v2"/>'
  };
  const svg = key => `<svg viewBox="0 0 16 16">${icons[key] || icons.features}</svg>`;

  function setOn(key, on) {
    const b = document.querySelector(`#dock .d-btn[data-key="${key}"]`);
    if (b) b.classList.toggle('on', !!on);
  }

  function toggleVoice() {
    if (global.VectorSpeech) {
      const on = global.VectorSpeech.toggle();
      setOn('mic', on);
    } else {
      V.state === 'listening' ? V.idle() : V.listen();
    }
  }

  function toggleSound() {
    if (!global.VectorAudio) return;
    const on = !global.VectorAudio.enabled;
    global.VectorAudio.setEnabled(on);
    setOn('sound', on);
  }

  function toggleCursor() {
    const C = global.VectorCursor;
    if (!C) return;
    if (C.mode === 'off') {
      C.mouse();
      setOn('hand', true);
    } else if (C.mode === 'mouse') {
      C.hand();
      setOn('hand', true);
    } else {
      C.off();
      setOn('hand', false);
    }
  }

  function buildDock() {
    const dock = document.getElementById('dock');
    if (!dock || dock.dataset.controls === 'ready') return;
    dock.dataset.controls = 'ready';
    dock.innerHTML = '';

    const items = [
      ['mic', 'VOICE', toggleVoice],
      ['sep'],
      ['screen', 'WORKSPACE', () => V.toggleWorkspace()],
      ['sep'],
      ['cam', 'VISION', () => { V.vision.toggle(); setOn('cam', V.vision.on); }],
      ['sep'],
      ['grid', 'SITUATION ROOM', () => V.situationRoom()],
      ['sep'],
      ['features', 'BACKEND FEATURES', () => V.openWidget('features')],
      ['sep'],
      ['features', 'MISSION CONTROL', () => V.openWidget('missioncontrol'), 'missioncontrol'],
      ['sep'],
      ['codegraph', 'CODE GRAPH', () => V.openWidget('codegraph')],
      ['sep'],
      ['answerengine', 'ANSWER ENGINE', () => V.openWidget('answerengine')],
      ['sep'],
      ['goalplanner', 'GOAL PLANNER', () => V.openWidget('goalplanner')],
      ['sep'],
      ['hand', 'POINTER', toggleCursor],
      ['sep'],
      ['sound', 'SOUND', toggleSound, null, true]
    ];

    items.forEach(item => {
      if (item[0] === 'sep') {
        dock.appendChild(Object.assign(document.createElement('div'), { className:'sep' }));
        return;
      }
      const key = item[3] || item[0];
      const b = document.createElement('button');
      b.className = 'd-btn';
      b.type = 'button';
      b.dataset.key = key;
      b.title = item[1];
      b.setAttribute('aria-label', item[1]);
      b.innerHTML = svg(item[0]);
      if (item[4]) b.classList.add('on');
      b.addEventListener('click', e => {
        e.stopPropagation();
        item[2]();
      });
      dock.appendChild(b);
    });

    V.on('state', ({to}) => setOn('mic', to === 'listening' || (global.VectorSpeech && global.VectorSpeech.active)));
    V.on('workspace', ({open}) => setOn('screen', open));
    V.on('vision', ({open}) => setOn('cam', open));
  }

  if (document.readyState !== 'loading') buildDock();
  else addEventListener('DOMContentLoaded', buildDock);

  global.VectorHudControls = { buildDock };
})(window);
