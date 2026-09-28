/* ============================================================================
   VECTOR · terminal.js  — hidden command terminal. Ctrl+Shift+H to summon.
   Type commands to open panels / drive VECTOR. `help` lists everything.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  const WIDGETS = [
    'chat','music','map','webcam','telemetry','market','goals','goalplanner',
    'districts','council','security','memory','memoryexplorer','cognition',
    'experiment','agentatlas','commandcenter','approvals','finance',
    'contentscheduler','answerengine','voicestudio','codegraph',
    'city3d',
    'librechat','openwebui','features','missioncontrol','corepanel','agentspanel','brainpanel',
    'knowledgepanel','codeintel','vectorcodepanel','trading','backtest',
    'hedgebot','intelligencepanel','shadowbroker','mediastudio','comfyui',
    'hyperframes','contentpanel','designpanel','researchpanel','pccontrol',
    'camerapanel','healthpanel','learningpanel','workpanel','privacypanel',
    'analyticspanel','personalpanel','platformpanel'
  ];
  let box=null, logEl=null, input=null, hist=[], hi=0;

  function build(){
    box=document.createElement('div'); box.id='cmd-terminal';
    box.setAttribute('role','dialog'); box.setAttribute('aria-label','VECTOR command terminal');
    box.innerHTML=`
      <div class="ct-head"><span class="ct-dot"></span><span class="ct-title">VECTOR ∷ COMMAND</span>
        <span class="ct-spacer"></span><span class="ct-hint">⌃⇧H</span><button type="button" class="ct-x" aria-label="Close terminal">✕</button></div>
      <div class="ct-log"></div>
      <div class="ct-row"><span class="ct-prompt">vector ❯</span><input class="ct-in" spellcheck="false"
        autocomplete="off" placeholder="type a command — try: help" aria-label="Command input" /></div>`;
    document.getElementById('stage').appendChild(box);
    logEl=box.querySelector('.ct-log'); input=box.querySelector('.ct-in');
    box.querySelector('.ct-x').addEventListener('click', ()=>toggle(false));
    drag(box, box.querySelector('.ct-head'));
    input.addEventListener('keydown', onKey);
    box.addEventListener('pointerdown', ()=>input.focus());
    print('VECTOR command interface · '+WIDGETS.length+' panels · type "help"', 'sys');
    return box;
  }

  function print(text, cls){ const d=document.createElement('div'); d.className='ct-line '+(cls||'');
    d.innerHTML=text; logEl.appendChild(d); logEl.scrollTop=logEl.scrollHeight; }

  function onKey(e){
    // Let the global Ctrl+Shift+H listener (bottom of this file) still see the
    // close shortcut, and treat Escape as "close" too — both used to be eaten
    // by the unconditional stopPropagation() below, so once the terminal input
    // had focus (i.e. right after typing any command) NEITHER shortcut could
    // close it anymore; only the mouse-only ✕ button worked (2026-07-17 browser
    // dogfood: Ctrl+Shift+H visibly failed to close the terminal after `open`
    // commands had been typed).
    if(e.ctrlKey && e.shiftKey && (e.key==='H'||e.key==='h')) return;
    if(e.key==='Escape'){ toggle(false); e.preventDefault(); return; }
    e.stopPropagation();
    if(e.key==='Enter'){ const v=input.value.trim(); if(v){ hist.push(v); hi=hist.length; print('<span class="ct-echo">vector ❯</span> '+esc(v),'echo'); run(v); } input.value=''; }
    else if(e.key==='ArrowUp'){ if(hi>0){ hi--; input.value=hist[hi]||''; } e.preventDefault(); }
    else if(e.key==='ArrowDown'){ if(hi<hist.length){ hi++; input.value=hist[hi]||''; } e.preventDefault(); }
    else if(e.key==='Tab'){ e.preventDefault(); const m=WIDGETS.filter(w=>w.startsWith(input.value.toLowerCase())); if(m.length===1) input.value=m[0]; }
  }

  function run(line){
    const parts=line.split(/\s+/); const cmd=parts[0].toLowerCase(); const arg=parts.slice(1).join(' ');
    const a1=(parts[1]||'').toLowerCase();
    switch(cmd){
      case 'help': return help();
      case 'clear': case 'cls': logEl.innerHTML=''; return;
      case 'ls': case 'panels': return print('panels · '+WIDGETS.join(' · '),'ok');
      case 'engage': case 'workspace': case 'hud': V.openWorkspace(); return ok('workspace engaged');
      case 'disengage': case 'collapse': V.closeWorkspace(); return ok('workspace collapsed');
      case 'open': case 'show': return openName(a1);
      case 'close': case 'hide': if(WIDGETS.includes(a1)){ V.closeWidget(a1); return ok('closed '+a1);} return err('unknown panel: '+a1);
      case 'vision': case 'camera': case 'cam':
        if(a1==='off'){ V.vision.close(); return ok('vision offline'); }
        V.vision.open(); return ok('vision online · cam hero');
      case 'situation': case 'situationroom': case 'warroom':
        V.situationRoom(); return ok('workspace ready · open a panel when needed');
      case 'voice': case 'listen-mode':
        if(global.VectorSpeech){ const on=global.VectorSpeech.toggle(); return ok('voice '+(on?'online · say “Hey VECTOR”':'offline')); }
        return err('speech recognition unavailable');
      case 'wake': V.wake(); return ok('online');
      case 'lock': case 'sleep': V.lock(); return ok('standby');
      case 'listen': V.listen(); return ok('listening — frame glows');
      case 'process': case 'think': V.process(); return ok('processing');
      case 'fortress': V.fortress(); return ok('FORTRESS — palm to unlock','warn');
      case 'say': case 'speak': if(!arg) return err('usage: say <text>'); V.say(arg); return;
      case 'do': case 'ask': case 'tell': case 'vector':
        if(!arg) return err('usage: do <instruction> — sends a command to VECTOR');
        ok('→ '+esc(arg));
        // Routes to /command: local HUD hits the laptop directly; HUD opened
        // through the cloud hits the brain queue → laptop executes (gateway-gated).
        Promise.resolve(V.command(arg))
          .then(r=>print('« '+esc(JSON.stringify(r)).slice(0,400),'ok'))
          .catch(e=>err('command failed: '+esc(String(e))));
        return;
      case 'map': V.showMap(arg?{label:arg.toUpperCase()}:undefined); return ok('tactical map');
      case 'connect': if(!parts[1]) return err('usage: connect <base-url> [api-key]');
        if(typeof V.setRuntimeMode === 'function') V.setRuntimeMode('connecting', parts[1]);
        V.connect({ base:parts[1], apiKey:parts[2]||'' }); return ok('connecting → '+parts[1]+' · waiting for backend health');
      case 'disconnect':
        V.disconnect();
        if(typeof V.setRuntimeMode === 'function') V.setRuntimeMode('demo', 'terminal disconnect · seed data only');
        return ok('disconnected · demo mode · seed data only');
      default:
        if(WIDGETS.includes(cmd)) return openName(cmd);
        return err('unknown command: '+esc(cmd)+' — type "help"');
    }
  }
  function openName(n){ if(!n) return err('usage: open <panel>');
    if(n==='vision'||n==='camera'){ V.vision.open(); return ok('vision online'); }
    if(!WIDGETS.includes(n)) return err('unknown panel: '+esc(n));
    V.openWidget(n);
    // Verify it actually rendered instead of claiming success unconditionally —
    // widgets.js openWidget() silently no-ops (console.warn only) for an id with
    // no factory function, and the old code always printed "opened <n>" either
    // way (2026-07-17 dogfood: the now-removed 'city3d' entry did exactly this).
    if(document.querySelector(`.widget[data-id="${n}"]`)) return ok('opened '+n);
    return err(n+' did not open — panel unavailable in this build'); }

  function help(){
    print('<b>COMMANDS</b>','sys');
    [['open &lt;panel&gt;','summon a panel  ('+WIDGETS.join(', ')+')'],
     ['close &lt;panel&gt;','dismiss a panel'],
     ['engage / disengage','reveal / hide the workspace HUD'],
     ['vision [off]','full-screen camera hero (orb to corner)'],
     ['map [place]','tactical map'],
     ['wake / lock / listen / fortress','drive the voice state'],
     ['say &lt;text&gt;','VECTOR speaks'],
     ['do &lt;instruction&gt;','send a command to VECTOR (works from any device)'],
     ['connect &lt;url&gt; [key]','attach the backend'],
     ['clear','wipe the log']
    ].forEach(([c,d])=>print('<span class="ct-cmd">'+c+'</span><span class="ct-desc">'+d+'</span>','help'));
  }
  function ok(m,cls){ print('› '+m, cls||'ok'); }
  function err(m){ print('✕ '+m,'err'); }
  function esc(s){ return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

  function drag(el, handle){ let s=null;
    handle.addEventListener('pointerdown',e=>{ if(e.target.closest('.ct-x'))return;
      const r=el.getBoundingClientRect(); s={dx:e.clientX-r.left,dy:e.clientY-r.top};
      el.style.transform='none'; handle.setPointerCapture(e.pointerId); });
    handle.addEventListener('pointermove',e=>{ if(!s)return;
      el.style.left=(e.clientX-s.dx)+'px'; el.style.top=(e.clientY-s.dy)+'px'; el.style.bottom='auto'; });
    handle.addEventListener('pointerup',()=>s=null); }

  let open=false, returnFocus=null;
  function toggle(force){ if(!box) build(); const next = force!=null?force:!open;
    if(next && !open) returnFocus = document.activeElement;
    open = next;
    box.classList.toggle('open', open);
    if(open) setTimeout(()=>input.focus(),30);
    else if(returnFocus && document.contains(returnFocus) && typeof returnFocus.focus==='function'){ returnFocus.focus(); returnFocus=null; }
  }

  // Capture phase (2026-07-19): with focus inside the cmd-bar input the
  // bubble-phase listener could be pre-empted by input handlers — ⌃⇧H
  // silently failed. Capture guarantees the terminal hotkey always works.
  addEventListener('keydown', e=>{
    if(e.ctrlKey && e.shiftKey && (e.key==='H'||e.key==='h')){ toggle(); e.preventDefault(); e.stopPropagation(); }
    else if(e.key==='Escape' && open){ toggle(false); }
  }, true);

  global.VectorTerminal = { toggle, run:(c)=>{ if(!box) build(); run(c); }, WIDGETS: WIDGETS.slice() };
})(window);
