/* ============================================================================
   VECTOR · provider-keys.js — Set/clear third-party provider API keys from the
   HUD, without touching .env or a terminal. Backed by GET/POST/DELETE
   /keys/providers (core/api/routers/keys.py) — allowlisted providers only,
   localhost-only, requires the current VECTOR_API_KEY to mutate.
   ========================================================================== */
(function (global) {
  'use strict';

  const V = global.VECTOR;
  if (!V) return;

  // ── Toggle button (fixed, top-right, consistent with cmd-bar styling) ─────
  const toggle = document.createElement('button');
  toggle.id = 'keys-panel-toggle';
  toggle.textContent = '🔑 KEYS';
  toggle.setAttribute('aria-label', 'Provider API keys');
  document.getElementById('stage').appendChild(toggle);

  const panel = document.createElement('div');
  panel.id = 'keys-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', 'Provider API keys');
  panel.hidden = true;
  panel.innerHTML =
    '<div id="keys-panel-head">' +
      '<span>PROVIDER KEYS</span>' +
      '<button id="keys-panel-close" aria-label="Close">✕</button>' +
    '</div>' +
    '<div id="keys-panel-list">Loading…</div>';
  document.getElementById('stage').appendChild(panel);

  const list = document.getElementById('keys-panel-list');
  let open = false;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  async function loadList() {
    list.innerHTML = 'Loading…';
    try {
      const data = await V.http('/keys/providers');
      const providers = Object.entries(data.providers || {}).sort((a, b) => a[0].localeCompare(b[0]));
      list.innerHTML = providers.map(([name, info]) => `
        <div class="keys-row" data-provider="${escapeHtml(name)}">
          <span class="keys-row-name">${escapeHtml(name)}</span>
          <span class="keys-row-status ${info.configured ? 'on' : 'off'}">${info.configured ? info.hint : 'not set'}</span>
          <button class="keys-row-btn" data-action="${info.configured ? 'clear' : 'set'}">${info.configured ? 'Clear' : 'Set'}</button>
        </div>`).join('');
    } catch (e) {
      list.innerHTML = '<div class="keys-row-error">Failed to load: ' + escapeHtml(String(e)) + '</div>';
    }
  }

  function startEdit(row, provider) {
    if (row.querySelector('.keys-row-input')) return; // already editing
    const input = document.createElement('input');
    input.type = 'password';
    input.className = 'keys-row-input';
    input.placeholder = 'paste key…';
    input.autocomplete = 'off';
    input.spellcheck = false;
    const confirmBtn = document.createElement('button');
    confirmBtn.className = 'keys-row-btn';
    confirmBtn.textContent = 'Save';
    confirmBtn.onclick = async () => {
      const value = input.value.trim();
      if (!value) return;
      confirmBtn.disabled = true;
      try {
        await V.http('/keys/providers/' + encodeURIComponent(provider), { method: 'POST', body: { value } });
        await loadList();
      } catch (e) {
        confirmBtn.disabled = false;
        input.placeholder = 'failed: ' + String(e).slice(0, 40);
      }
    };
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') confirmBtn.click();
      e.stopPropagation();
    });
    row.appendChild(input);
    row.appendChild(confirmBtn);
    input.focus();
  }

  async function clearKey(provider) {
    try {
      await V.http('/keys/providers/' + encodeURIComponent(provider), { method: 'DELETE' });
      await loadList();
    } catch (e) {
      console.warn('[VECTOR] clear key failed', e);
    }
  }

  list.addEventListener('click', e => {
    const btn = e.target.closest('.keys-row-btn[data-action]');
    if (!btn) return;
    const row = btn.closest('.keys-row');
    const provider = row.dataset.provider;
    if (btn.dataset.action === 'set') startEdit(row, provider);
    else clearKey(provider);
  });

  function openPanel() {
    open = true;
    panel.hidden = false;
    loadList();
  }
  function closePanel() {
    open = false;
    panel.hidden = true;
  }

  toggle.addEventListener('click', () => (open ? closePanel() : openPanel()));
  document.getElementById('keys-panel-close').addEventListener('click', closePanel);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && open) closePanel();
  });

  // ── CSS (injected inline so the module is self-contained) ─────────────────
  const style = document.createElement('style');
  style.textContent = `
#keys-panel-toggle {
  position: fixed;
  top: 14px;
  right: 14px;
  background: rgba(0,8,24,.82);
  border: 1px solid rgba(0,204,255,.22);
  border-radius: 6px;
  color: #00ccff;
  font: 11px 'JetBrains Mono', 'Courier New', monospace;
  letter-spacing: .04em;
  padding: 6px 10px;
  cursor: pointer;
  z-index: 9900;
  backdrop-filter: blur(8px);
}
#keys-panel-toggle:hover { background: rgba(0,204,255,.12); }
#keys-panel {
  position: fixed;
  top: 48px;
  right: 14px;
  width: min(380px, calc(100vw - 28px));
  max-height: 70vh;
  overflow-y: auto;
  background: rgba(0,8,24,.92);
  border: 1px solid rgba(0,204,255,.22);
  border-radius: 6px;
  backdrop-filter: blur(8px);
  z-index: 9900;
  box-shadow: 0 0 16px rgba(0,204,255,.08);
}
#keys-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(0,204,255,.15);
  color: #b0e8ff;
  font: 11px 'JetBrains Mono', monospace;
  letter-spacing: .08em;
}
#keys-panel-close {
  background: none;
  border: none;
  color: #b0e8ff;
  cursor: pointer;
  font-size: 13px;
}
#keys-panel-list { padding: 6px; }
.keys-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  border-bottom: 1px solid rgba(0,204,255,.08);
  flex-wrap: wrap;
}
.keys-row-name {
  flex: 1;
  color: #b0e8ff;
  font: 11px 'JetBrains Mono', monospace;
}
.keys-row-status {
  font: 10px 'JetBrains Mono', monospace;
}
.keys-row-status.on  { color: #00cc88; }
.keys-row-status.off { color: rgba(176,232,255,.4); }
.keys-row-btn {
  background: none;
  border: 1px solid rgba(0,204,255,.35);
  border-radius: 4px;
  color: #00ccff;
  font-size: 10px;
  padding: 2px 8px;
  cursor: pointer;
}
.keys-row-btn:hover { background: rgba(0,204,255,.12); }
.keys-row-btn:disabled { opacity: .4; cursor: default; }
.keys-row-input {
  flex: 1 0 100%;
  background: rgba(0,0,0,.3);
  border: 1px solid rgba(0,204,255,.3);
  border-radius: 4px;
  color: #b0e8ff;
  font: 11px 'JetBrains Mono', monospace;
  padding: 3px 6px;
  outline: none;
}
.keys-row-error { color: #ff4466; font: 11px 'JetBrains Mono', monospace; padding: 8px; }
@media (max-width: 480px) {
  #keys-panel { top: 44px; right: 8px; left: 8px; width: auto; }
}`;
  document.head.appendChild(style);

  global.VectorProviderKeys = { open: openPanel, close: closePanel };
})(window);
