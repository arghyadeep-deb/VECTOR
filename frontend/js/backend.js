/* ============================================================================
   VECTOR · backend.js  —  live data polling + WS event wiring
   Loaded after all other modules. Listens for the 'connected' event that
   VECTOR.html's autoConnect() already fires, then polls 30+ endpoints and
   pushes real data into D.* and the open widget DOM.
   Falls back silently — seed data from data.js is always the safety net.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  const D = global.VECTOR_DATA;
  if (!V || !D) return;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function relTime(iso) {
    if (!iso) return '—';
    try {
      const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
      if (diff < 60) return diff + 's';
      if (diff < 3600) return Math.floor(diff / 60) + 'm';
      if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
      return Math.floor(diff / 86400) + 'd ago';
    } catch (_) { return '—'; }
  }

  function fmtUptime(s) {
    s = Math.floor(s || 0);
    return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60]
      .map(n => String(n).padStart(2, '0')).join(':');
  }

  // HP → tier string (mirrors data.js mapping)
  function hpTier(hp) {
    if (hp >= 800) return 'ELITE';
    if (hp >= 700) return 'STRONG';
    if (hp >= 500) return 'HEALTHY';
    if (hp >= 300) return 'WEAK';
    if (hp > 0)   return 'CRITICAL';
    return 'GHOST';
  }

  // ── Data adapters (API format → widget format) ────────────────────────────

  function adaptAgent(a) {
    return {
      id: a.id || a.agent_id,
      name: a.name || 'Agent',
      district: a.district || 'unknown',
      health_points: a.health_points ?? 500,
      generation: a.generation ?? 1,
      tier: a.tier || hpTier(a.health_points ?? 500),
      model: a.model || 'vector-focus',
      last_active: relTime(a.last_active),
    };
  }

  // Flat list [{horizon:'MID', ...}] → {LONG:[], MID:[], SHORT:[]}
  function adaptGoals(list) {
    const out = { LONG: [], MID: [], SHORT: [] };
    (list || []).forEach(g => {
      const h = (g.horizon || 'SHORT').toUpperCase();
      if (out[h]) out[h].push({
        id: g.id,
        title: g.title || g.action || '—',
        progress: g.progress ?? 0,
        tags: g.tags || [],
      });
    });
    return out;
  }

  // ISO timestamp + event_type → importance label
  function inferImportance(ev) {
    if (/ANOMALY|CRITICAL|ERROR/.test(ev)) return 'critical';
    if (/DECISION|HP_CHANGED|HYPOTHESIS/.test(ev)) return 'high';
    return 'normal';
  }

  function adaptMemory(events) {
    return (events || []).map(e => ({
      event_type: e.event_type || 'EVENT',
      content: e.content || '',
      importance: inferImportance(e.event_type || ''),
      when: relTime(e.timestamp),
    }));
  }

  // Dict params → display string (security widget expects a plain string)
  function fmtParams(params) {
    if (typeof params === 'string') return params;
    if (!params) return '';
    const vals = Object.values(params);
    return vals.length ? vals.join(' ') : JSON.stringify(params);
  }

  // ── Widget DOM refreshers ─────────────────────────────────────────────────
  // All use data-id="id" on the widget wrapper (set by shell() in widgets.js)

  function qs(wid, sel) {
    return document.querySelector(`[data-id="${wid}"] ${sel}`);
  }
  function qsa(wid, sel) {
    return document.querySelectorAll(`[data-id="${wid}"] ${sel}`);
  }
  function widgetOpen(id) {
    return !!document.querySelector(`[data-id="${id}"]`);
  }

  function refreshDistricts() {
    if (!widgetOpen('districts')) return;
    const grid = qs('districts', '.grid');
    if (!grid) return;
    grid.innerHTML = D.agents.slice(0, 18).map(a => {
      const pct = Math.max(0, Math.min(100, a.health_points / 10));
      const cls = a.health_points <= 0 ? 'ghost' : '';
      const bar = a.health_points <= 0 ? 'low' : a.health_points < 400 ? 'low' : a.health_points < 700 ? 'mid' : '';
      return `<div class="agent ${cls}">
        <div class="an">${a.name}</div><div class="ad">${a.district.toUpperCase()}</div>
        <div class="hpbar ${bar}"><i style="width:${pct}%"></i></div>
        <div class="hp"><span>HP ${a.health_points}</span><span>G${a.generation} · ${a.tier}</span></div>
      </div>`;
    }).join('');
  }

  function refreshGoals() {
    if (!widgetOpen('goals')) return;
    const body = qs('goals', '.w-body');
    if (!body) return;
    body.innerHTML = ['LONG', 'MID', 'SHORT'].map(h => {
      const items = (D.GOALS[h] || []).map(g =>
        `<div class="row-kv"><span class="v">${g.title}</span><span class="k">${Math.round(g.progress * 100)}%</span></div>
         <div class="meter ${g.progress < 0.4 ? 'dn' : g.progress < 0.7 ? 'warn' : ''}"><i style="width:${g.progress * 100}%"></i></div>`
      ).join('');
      return `<div style="font-size:8px;letter-spacing:.16em;color:var(--txt-faint);margin:6px 0 3px">${h} HORIZON</div>${items}`;
    }).join('');
  }

  function refreshMemory() {
    if (!widgetOpen('memory')) return;
    const body = qs('memory', '.w-body');
    if (!body) return;
    body.innerHTML = D.MEMORY.slice(0, 20).map(m =>
      `<div class="mevt imp-${m.importance}">
        <span class="ew">${m.when}</span>
        <div class="et">${m.event_type}</div>
        <div class="ec">${m.content}</div>
      </div>`
    ).join('');
  }

  function refreshCouncil() {
    if (!widgetOpen('council')) return;
    const body = qs('council', '.w-body');
    if (!body) return;
    body.innerHTML = D.COUNCIL.slice(0, 5).map(c =>
      `<div class="csess">
        <div class="q">${c.question}</div>
        <div class="meta">
          <span class="badge2 ${c.recommendation}">${(c.recommendation || 'defer').toUpperCase()}</span>
          <span class="badge2 ${c.stakes === 'critical' ? 'crit' : c.stakes || 'high'}">${(c.stakes || 'high').toUpperCase()}</span>
          <span class="k" style="margin-left:auto">${Math.round((c.confidence || 0) * 100)}% · ${c.when || '—'}</span>
        </div>
      </div>`
    ).join('');
  }

  function refreshThreat(level) {
    if (!widgetOpen('security')) return;
    const el = qs('security', '.v');
    if (!el) return;
    const colors = { low: 'var(--ok)', medium: 'var(--warn)', high: 'var(--danger)', critical: 'var(--danger)' };
    el.style.color = colors[level] || 'var(--ok)';
    el.textContent = (level || 'low').toUpperCase();
  }

  // Telemetry: widgets.js animateTelemetry already updates these via setInterval.
  // We shadow its values by writing the same data-* selectors directly.
  // For uptime and tick we use real backend values; CPU/VRAM/TEMP come from /sensing/status.
  function setTel(sel, val) {
    const e = document.querySelector(`[data-id="telemetry"] ${sel}`);
    if (e) e.textContent = val;
  }
  function setBar(sel, pct) {
    const e = document.querySelector(`[data-id="telemetry"] ${sel}`);
    if (e) e.style.width = Math.min(100, Math.max(0, pct)) + '%';
  }

  // ── Poll helpers ──────────────────────────────────────────────────────────

  let _tick = 0;

  async function poll(path, interval, handler) {
    async function run() {
      try {
        const data = await V.http(path);
        handler(data);
      } catch (_) { /* silent — seed data stays */ }
    }
    run();
    setInterval(run, interval);
  }

  // ── Main polling setup ────────────────────────────────────────────────────

  function startPolling() {

    // /status — 5s — uptime, agent count, loop state
    poll('/status', 5000, data => {
      if (!data) return;
      setTel('[data-up]', fmtUptime(data.uptime_seconds));
      if (data.agents) {
        setTel('[data-tick]', String(_tick++));
      }
    });

    // /agents — 8s — districts panel
    poll('/agents', 8000, data => {
      const list = data.agents || data || [];
      if (!Array.isArray(list) || list.length === 0) return;
      D.agents = list.map(adaptAgent);
      refreshDistricts();
      // also update city3d if open
      if (global.VectorCity) global.VectorCity.updateAgents(D.agents);
    });

    // /memory/recent — 6s — memory panel
    // endpoint returns {memories:[...]} (confirmed by web_ui.py)
    poll('/memory/recent?limit=25', 6000, data => {
      const events = data.memories || data.events || data.items || (Array.isArray(data) ? data : []);
      if (!Array.isArray(events) || events.length === 0) return;
      D.MEMORY = adaptMemory(events);
      refreshMemory();
    });

    // /brain/goals — 10s — goals panel (returns flat list with horizon field)
    poll('/brain/goals', 10000, data => {
      const list = data.goals || data.actions || data || [];
      if (!Array.isArray(list) || list.length === 0) return;
      D.GOALS = adaptGoals(list);
      refreshGoals();
    });

    // /security/status — 12s — threat level
    poll('/security/status', 12000, data => {
      if (!data) return;
      refreshThreat(data.threat_level);
    });

    // /memory/council/history — 20s — council panel
    poll('/memory/council/history', 20000, data => {
      const sessions = data.sessions || data.events || data || [];
      if (!Array.isArray(sessions) || sessions.length === 0) return;
      D.COUNCIL = sessions.slice(0, 5).map(s => ({
        question: s.question || s.content || '—',
        recommendation: s.recommendation || s.decision || 'defer',
        stakes: s.stakes || 'high',
        confidence: s.confidence || 0,
        when: relTime(s.timestamp || s.created_at),
      }));
      refreshCouncil();
    });

    // /sensing/status — 15s — CPU/RAM/GPU for telemetry
    poll('/sensing/status', 15000, data => {
      if (!data) return;
      const cpu = data.cpu_percent ?? data.cpu;
      const ram = data.ram_percent ?? data.ram;
      const gpu = data.gpu_percent ?? data.gpu;
      const temp = data.gpu_temp ?? data.temp;
      if (cpu != null) { setTel('[data-cpu]', cpu.toFixed(0) + '%'); setBar('[data-cpu-bar]', cpu); }
      if (ram != null) { setTel('[data-vram]', ram.toFixed(0) + '% · 16GB'); setBar('[data-vram-bar]', ram); }
      if (temp != null) { setTel('[data-temp]', temp.toFixed(0) + '°C'); setBar('[data-temp-bar]', (temp - 40) / 40 * 100); }
    });

    // /loop/status — 8s — loop tick counter
    poll('/loop/status', 8000, data => {
      if (!data) return;
      const tick = data.tick_count ?? data.ticks;
      if (tick != null) { _tick = tick; setTel('[data-tick]', tick); }
    });

    // Background-only polls — data stored in D.* for future widgets
    const bg = [
      ['/tasks/',               15000, d => D.TASKS    = d.tasks    || d || []],
      ['/inference/stats',      12000, d => D.INFERENCE = d || {}],
      ['/channels/status',      15000, d => D.CHANNELS  = d.channels || d || []],
      ['/scheduler/jobs',       15000, d => D.JOBS      = d.jobs     || d || []],
      ['/audit/recent',         20000, d => D.AUDIT     = d.entries  || d || []],
      ['/network/peers',        25000, d => D.PEERS     = d.peers    || d || []],
      ['/metering/status',      15000, d => D.METERING  = d || {}],
      ['/sandbox/status',       25000, d => D.SANDBOX   = d || {}],
      ['/mcp/status',           20000, d => D.MCP       = d || {}],
      ['/research/status',      20000, d => D.RESEARCH  = d || {}],
      ['/email/recent',         20000, d => D.EMAIL     = d.emails   || d || []],
      ['/providers/routes',     20000, d => D.PROVIDERS = d.routes   || d || []],
      ['/tools/registry',       20000, d => D.TOOLS     = d.tools    || d || []],
      ['/mining/status',        20000, d => D.MINING    = d || {}],
      ['/migration/sources',    30000, d => D.MIGRATION = d || {}],
      ['/oauth/integrations',   30000, d => D.OAUTH     = d.integrations || d || []],
    ];
    bg.forEach(([path, ms, handler]) => poll(path, ms, handler));
  }

  // ── Real-time WS event handlers ───────────────────────────────────────────

  V.on('state_event', function (ev) {
    if (!ev || !ev.event_type) return;
    const type = ev.event_type;
    const data = ev.data || {};

    if (type === 'AGENT_HP_CHANGED') {
      // Update in-place so the widget refreshes only the one bar
      const agent = D.agents.find(a => a.id === data.agent_id);
      if (agent) {
        agent.health_points = data.new_hp ?? data.hp ?? agent.health_points;
        agent.tier = hpTier(agent.health_points);
        refreshDistricts();
        if (global.VectorCity) global.VectorCity.updateAgentHP(data.agent_id, agent.health_points);
      }

    } else if (type === 'DECISION_MADE' || type === 'TASK_ROUTED') {
      D.MEMORY.unshift({
        event_type: type,
        content: data.action || data.task || data.content || '',
        importance: 'high',
        when: 'now',
      });
      D.MEMORY = D.MEMORY.slice(0, 50);
      refreshMemory();
      if (global.VectorCity && type === 'TASK_ROUTED') {
        global.VectorCity.addFlightArc(data.from_district, data.to_district);
      }

    } else if (type === 'ANOMALY_DETECTED') {
      refreshThreat('high');
      V.emit('notify', ev);

    } else if (type === 'HYPOTHESIS_SURFACED') {
      V.emit('notify', ev);
    }
  });

  // /ws main channel sends {type:'status'} every 2s — use for real-time uptime
  V.on('status', function (msg) {
    if (!msg) return;
    if (msg.uptime_seconds != null) setTel('[data-up]', fmtUptime(msg.uptime_seconds));
    if (msg.agents?.count != null) {
      // Update ticker bottom strip — find "DISTRICTS ONLINE" span if present
      const strip = document.querySelector('#newsTrack');
      if (strip && strip.textContent.includes('DISTRICTS')) {
        // Don't rewrite the whole ticker — just let the next status refresh handle it
      }
    }
  });

  // ── Boot: start on 'connected' (already fired by VECTOR.html autoConnect) ─

  V.on('connected', function () {
    console.info('[VECTOR] backend.js: polling started');
    startPolling();
  });

})(window);
