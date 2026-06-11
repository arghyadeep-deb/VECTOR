/* ============================================================================
   VECTOR · backend.js  —  live data polling + WS event wiring
   Loaded after all other modules. Listens for the 'connected' event that
   VECTOR.html's autoConnect() already fires, then polls 30+ endpoints and
   pushes real data into D.* and the open widget DOM.
   Poll failures are surfaced through VECTOR.setRuntimeMode when available;
   seed data from data.js remains visible as explicit demo/degraded state.
   ========================================================================== */
(function (global) {
  'use strict';
  const V = global.VECTOR;
  const D = global.VECTOR_DATA;
  if (!V || !D) return;

  // ── Helpers ──────────────────────────────────────────────────────────────

  // HTML-escape any value before it enters innerHTML. Covers text AND
  // attribute context (escapes quotes too). Backend data is owner-trusted but
  // VECTOR ingests external content (emails, Reddit/HN, scrapes) that can flow
  // into these fields — defense-in-depth against stored XSS in our own HUD.
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

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
        <div class="an">${esc(a.name)}</div><div class="ad">${esc(String(a.district || '').toUpperCase())}</div>
        <div class="hpbar ${bar}"><i style="width:${pct}%"></i></div>
        <div class="hp"><span>HP ${esc(a.health_points)}</span><span>G${esc(a.generation)} · ${esc(a.tier)}</span></div>
      </div>`;
    }).join('');
  }

  function refreshGoals() {
    if (!widgetOpen('goals')) return;
    const body = qs('goals', '.w-body');
    if (!body) return;
    body.innerHTML = ['LONG', 'MID', 'SHORT'].map(h => {
      const items = (D.GOALS[h] || []).map(g =>
        `<div class="row-kv"><span class="v">${esc(g.title)}</span><span class="k">${Math.round(g.progress * 100)}%</span></div>
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
      `<div class="mevt imp-${esc(m.importance)}">
        <span class="ew">${esc(m.when)}</span>
        <div class="et">${esc(m.event_type)}</div>
        <div class="ec">${esc(m.content)}</div>
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

  function setTelLabel(labelText, val) {
    if (!widgetOpen('telemetry')) return;
    document.querySelectorAll('[data-id="telemetry"] .row-kv').forEach(row => {
      const k = row.querySelector('.k');
      if (k && k.textContent.trim() === labelText) {
        const v = row.querySelector('.v');
        if (v) v.textContent = val;
      }
    });
  }

  // ── Live security approvals from audit_log ────────────────────────────────
  function adaptApprovals(auditLog) {
    return (auditLog || []).filter(e =>
      e.color === 'YELLOW' || e.color === 'RED' || e.level === 'YELLOW' || e.level === 'RED'
    ).slice(0, 5).map(e => ({
      action_id: e.action_id || e.id || ('act_' + Math.random().toString(36).substr(2, 5)),
      action_type: e.action_type || e.action || '—',
      params: fmtParams(e.params || e.payload || ''),
      level: e.color || e.level || 'YELLOW',
      proposed_by: e.agent || e.proposed_by || 'VECTOR',
      expires: e.expires_in || 30,
    }));
  }

  // Live per-second countdown for pending approval expiry — ticks all
  // `.exp[data-expires-at]` spans down to 0 between poll refreshes, since
  // the backend only reports a snapshot "expires in Ns" on each poll.
  function tickApprovalCountdowns() {
    const body = qs('security', '.w-body');
    if (!body) return;
    body.querySelectorAll('.exp[data-expires-at]').forEach(el => {
      const expiresAt = Number(el.dataset.expiresAt);
      const remaining = Math.max(0, Math.round((expiresAt - Date.now()) / 1000));
      el.textContent = remaining + 's';
      if (remaining <= 0) {
        const row = el.closest('.appr');
        if (row) row.style.opacity = '.3';
      }
    });
  }
  setInterval(tickApprovalCountdowns, 1000);

  function refreshApprovals(approvals) {
    if (!widgetOpen('security')) return;
    const body = qs('security', '.w-body');
    if (!body) return;
    let apprEl = body.querySelector('.approvals-live');
    if (!apprEl) { apprEl = document.createElement('div'); apprEl.className = 'approvals-live'; body.appendChild(apprEl); }
    if (!approvals.length) { apprEl.innerHTML = ''; return; }
    apprEl.innerHTML =
      `<div style="font-size:8px;letter-spacing:.16em;color:var(--txt-faint);margin:8px 0 4px">LIVE PENDING · ${approvals.length}</div>` +
      approvals.map(a => {
        const isRed = a.level === 'RED';
        const expiresAt = Date.now() + (Number(a.expires) || 0) * 1000;
        return `<div class="appr ${isRed ? 'red' : ''}" style="margin-bottom:4px">
          <div class="at">${a.action_type} <span class="badge2 ${isRed ? 'crit' : 'high'}">${a.level}</span></div>
          <div class="ap">${a.params} · by ${a.proposed_by}</div>
          <div class="acts">
            <button class="ok2 live-appr-ok" data-action-id="${a.id || a.action_id || a.action_type}" data-atype="${a.action_type}">APPROVE</button>
            <button class="no2 live-appr-no" data-action-id="${a.id || a.action_id || a.action_type}">DENY</button>
            <span class="exp" data-expires-at="${expiresAt}">${a.expires}s</span>
          </div></div>`;
      }).join('');
    tickApprovalCountdowns();
    apprEl.querySelectorAll('.live-appr-ok').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const atype = btn.dataset.atype;
        const id = btn.dataset.actionId || atype;
        V.http('/gateway/approve/' + encodeURIComponent(id), { method: 'POST', body: {} }).catch(() => {});
        btn.closest('.appr').style.opacity = '.3';
        if (V.say) V.say('Approved. ' + atype + ' executing.');
      });
    });
    apprEl.querySelectorAll('.live-appr-no').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const id = btn.dataset.actionId;
        V.http('/gateway/reject/' + encodeURIComponent(id), { method: 'POST', body: {} }).catch(() => {});
        btn.closest('.appr').style.opacity = '.3';
        if (V.say) V.say('Denied.');
      });
    });
  }

  // ── Live market ticker ─────────────────────────────────────────────────────
  function refreshMarket(quotes) {
    if (!widgetOpen('market')) return;
    const statEl = qs('market', '.stat');
    if (!statEl || !quotes || !quotes.length) return;
    const nifty = quotes.find(q => /nifty|nsei|nse|^nsei/i.test(q.symbol)) || quotes[0];
    if (!nifty) return;
    const pct = nifty.change_pct != null ? nifty.change_pct : (nifty.change_percent != null ? nifty.change_percent : null);
    const chg = nifty.change != null ? nifty.change : '';
    const pos = pct == null || pct >= 0;
    statEl.innerHTML =
      `<div><b>${nifty.symbol}</b> <span>${nifty.price != null ? nifty.price : (nifty.close != null ? nifty.close : '—')}</span></div>
       <div style="color:var(--${pos ? 'ok' : 'danger'})"><b>${pos ? '▲' : '▼'} ${pct != null ? Math.abs(pct).toFixed(2) : '—'}%</b> <span>${chg}</span></div>`;
  }

  // ── Poll helpers ──────────────────────────────────────────────────────────

  let _tick = 0;
  let pollingStarted = false;
  const pollTimers = [];
  let successfulPolls = 0;
  let failedPolls = 0;

  function markRuntime(mode, detail) {
    if (typeof V.setRuntimeMode === 'function') V.setRuntimeMode(mode, detail);
  }

  async function poll(path, interval, handler) {
    async function run() {
      try {
        const data = await V.http(path);
        successfulPolls += 1;
        failedPolls = 0;
        markRuntime('live', V.config.base || path);
        handler(data);
      } catch (err) {
        failedPolls += 1;
        const detail = path + ' failed' + (err && err.message ? ': ' + err.message : '');
        if (!successfulPolls || failedPolls >= 2) markRuntime('degraded', detail);
      }
    }
    run();
    pollTimers.push(setInterval(run, interval));
  }

  // ── Main polling setup ────────────────────────────────────────────────────

  function startPolling() {
    if (pollingStarted) return;
    pollingStarted = true;

    // /status — 5s — uptime, agent count, loop state
    poll('/status', 5000, data => {
      if (!data) return;
      setTel('[data-up]', fmtUptime(data.uptime_seconds));
      if (data.agents) {
        setTel('[data-tick]', String(_tick++));
      }
    });

    // /world/snapshot — 5s — unified live context shared by HUD panels
    poll('/world/snapshot', 5000, data => {
      if (!data) return;
      D.WORLD = data;
      if (data.runtime && data.runtime.uptime_seconds != null) {
        setTel('[data-up]', fmtUptime(data.runtime.uptime_seconds));
      }
      if (data.agents && Array.isArray(data.agents.sample) && data.agents.sample.length) {
        D.agents = data.agents.sample.map(adaptAgent);
        refreshDistricts();
        if (global.VectorCity) global.VectorCity.updateAgents(D.agents);
      }
      if (data.memory && Array.isArray(data.memory.recent) && data.memory.recent.length) {
        D.MEMORY = adaptMemory(data.memory.recent);
        refreshMemory();
      }
      if (data.safety && Array.isArray(data.safety.pending_approvals)) {
        D.APPROVALS = data.safety.pending_approvals;
        refreshApprovals(D.APPROVALS);
      }
      if (data.sensing && data.sensing.system_load) {
        const load = data.sensing.system_load;
        if (load.cpu_percent != null) setTel('[data-cpu]', Number(load.cpu_percent).toFixed(0) + '%');
        if (load.mem_used_percent != null) setTel('[data-vram]', Number(load.mem_used_percent).toFixed(0) + '%');
      }
      const glyph = document.getElementById('glyphNet');
      if (glyph) glyph.textContent = 'WORLD · ' + String(data.status || 'OK').toUpperCase();
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

    // /brain/reasoning/chains - 15s - decision trace state for brain panels
    poll('/brain/reasoning/chains?limit=20', 15000, data => {
      const chains = data && (data.chains || data.decisions || data.items || (Array.isArray(data) ? data : []));
      if (!Array.isArray(chains)) return;
      D.DECISIONS = chains.slice(0, 20);
    });

    // /brain/persons - 30s - person graph state for relationship-aware UI
    poll('/brain/persons', 30000, data => {
      const persons = data && (data.persons || data.items || (Array.isArray(data) ? data : []));
      if (!Array.isArray(persons)) return;
      D.PERSONS = persons;
    });

    // /security/status — 12s — threat level + live audit log
    poll('/security/status', 12000, data => {
      if (!data) return;
      refreshThreat(data.threat_level);
      if (data.audit_log) {
        D.APPROVALS = adaptApprovals(data.audit_log);
        refreshApprovals(D.APPROVALS);
      }
    });

    // /gateway/pending - 5s - canonical owner approval queue
    poll('/gateway/pending', 5000, data => {
      const pending = data && (data.pending || data.items || (Array.isArray(data) ? data : []));
      if (!Array.isArray(pending)) return;
      D.APPROVALS = pending;
      refreshApprovals(D.APPROVALS);
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

    // /inference/stats — 12s — active model name in telemetry
    poll('/inference/stats', 12000, data => {
      D.INFERENCE = data || {};
      const model = data && (data.active_model || data.current_model || data.model);
      if (model) setTelLabel('ACTIVE MODEL', model);
      const cost = data && (data.cost_inr || data.total_cost_inr);
      if (cost != null) setTelLabel('INR COST', '₹' + cost.toFixed(4));
    });

    // /finance/ticker — 30s — live NSE market data
    poll('/finance/ticker?symbols=^NSEI,RELIANCE.NS,TCS.NS,NVDA', 30000, data => {
      const quotes = data && (data.quotes || (Array.isArray(data) ? data : []));
      if (quotes && quotes.length) {
        D.STOCKS_LIVE = quotes;
        refreshMarket(quotes);
      }
    });

    // /brain/hypotheses (surfaced) — 25s — append to memory widget
    poll('/notifications/hypotheses', 25000, data => {
      const items = data && (data.hypotheses || data || []);
      if (!Array.isArray(items) || !items.length) return;
      items.slice(0, 3).forEach(h => {
        D.MEMORY.unshift({
          event_type: 'HYPOTHESIS_SURFACED',
          content: h.statement || h.hypothesis || h.content || '—',
          importance: 'normal',
          when: relTime(h.surfaced_at || h.timestamp),
        });
      });
      D.MEMORY = D.MEMORY.slice(0, 50);
      refreshMemory();
    });

    // /nudge/latest — 25s — behavioral nudges in memory feed
    poll('/nudge/latest', 25000, data => {
      const nudge = data && (data.nudge || data.message);
      if (!nudge) return;
      D.MEMORY.unshift({ event_type: 'NUDGE', content: nudge, importance: 'normal', when: 'now' });
      D.MEMORY = D.MEMORY.slice(0, 50);
      refreshMemory();
    });

    // Background-only polls — data stored in D.* for future widgets
    const bg = [
      ['/tasks/',               15000, d => D.TASKS    = d.tasks    || d || []],
      ['/inference/stats',      60000, d => D.INFERENCE = d || {}],  // shadowed by active poll above
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

  V.on('decision_made', function (msg) {
    const data = msg && (msg.data || msg.decision || msg);
    if (!data) return;
    D.DECISIONS = [data].concat(D.DECISIONS || []).slice(0, 20);
    D.MEMORY.unshift({
      event_type: 'DECISION_MADE',
      content: data.action || data.summary || data.content || data.id || '',
      importance: 'high',
      when: 'now',
    });
    D.MEMORY = D.MEMORY.slice(0, 50);
    refreshMemory();
  });

  V.on('hypothesis_surfaced', function (msg) {
    const data = msg && (msg.data || msg.hypothesis || msg);
    if (!data) return;
    D.MEMORY.unshift({
      event_type: 'HYPOTHESIS_SURFACED',
      content: data.statement || data.hypothesis || data.content || '',
      importance: 'normal',
      when: 'now',
    });
    D.MEMORY = D.MEMORY.slice(0, 50);
    refreshMemory();
  });

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

    } else if (type === 'CITY_UPDATE') {
      // From websocket_broadcaster.city_update() — bulk district HP update
      const districts = data.districts || [];
      districts.forEach(d => {
        const agent = D.agents.find(a => a.district === d.name);
        if (agent) { agent.health_points = d.hp ?? agent.health_points; agent.tier = hpTier(agent.health_points); }
      });
      refreshDistricts();
      if (global.VectorCity) global.VectorCity.updateAgents(D.agents);
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

  // ── Wire city_update from websocket_broadcaster.py ───────────────────────
  // websocket_broadcaster sends {type:'city_update', districts:[{name, hp, ...}]}
  // over the main /ws channel. vector-core.js only handles known types; unknown
  // types are dropped. We intercept by listening to the raw WS message ourselves
  // via the 'ws:open' event — but since we can't attach to the raw socket, we
  // patch the 'connected' event to intercept the socket ref instead.
  // Simpler: re-open a shadow listener on the same /ws socket is not possible.
  // Instead, websocket_broadcaster's city_update is also surfaced through
  // /ws/state AGENT_HP_CHANGED events which city3d.js already handles.
  // ADDITIONALLY: the main /ws sends {type:'events'} every 5s with recent episodes.
  // Wire that into D.MEMORY as well so memory widget stays fresh between polls.
  V.on('status', function (msg) {
    if (!msg) return;
    // {type:'status', uptime_seconds, agents:{count, list}} from main /ws every 2s
    if (msg.uptime_seconds != null) setTel('[data-up]', fmtUptime(msg.uptime_seconds));
    // agents list in status message — update D.agents silently
    if (msg.agents && Array.isArray(msg.agents.list) && msg.agents.list.length > 0) {
      D.agents = msg.agents.list.map(adaptAgent);
      refreshDistricts();
      if (global.VectorCity) global.VectorCity.updateAgents(D.agents);
    }
  });

  // {type:'events'} from main /ws — episodic events burst
  V.on('response', function () {}); // already handled by vector-core.js (say)

  // ── Boot: start on 'connected' (already fired by VECTOR.html autoConnect) ─

  V.on('connected', function () {
    console.info('[VECTOR] backend.js: polling started');
    markRuntime('connecting', V.config.base || 'backend');
    startPolling();
  });

})(window);
