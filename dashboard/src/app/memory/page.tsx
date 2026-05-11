'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/hud/Sidebar';
import { api, formatTs, type MemoryEvent } from '@/lib/api';

const TYPE_COLOR: Record<string, string> = {
  interaction: 'chip-cyan', action: 'chip-blue', system: 'chip-muted',
  council_session: 'chip-amber', security_scan: 'chip-red',
};
const IMP_COLOR: Record<string, string> = {
  HIGH: 'var(--cyan)', MED: 'var(--on-muted)', LOW: 'var(--outline)',
};

export default function MemoryPage() {
  const [events, setEvents]   = useState<MemoryEvent[]>([]);
  const [count,  setCount]    = useState(0);
  const [query,  setQuery]    = useState('');
  const [error,  setError]    = useState('');
  const [loading,setLoading]  = useState(true);

  const load = useCallback(async () => {
    try {
      const d = await api.memoryRecent(30);
      setEvents(d.events ?? []);
      setCount(d.count ?? 0);
      setError('');
    } catch (e: unknown) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 10000); return () => clearInterval(id); }, [load]);

  const filtered = query
    ? events.filter(e => e.content?.toLowerCase().includes(query.toLowerCase()) || e.event_type?.toLowerCase().includes(query.toLowerCase()))
    : events;

  const types = [...new Set(events.map(e => e.event_type))];

  return (
    <div className="hud-layout">
      <Sidebar />
      <main className="hud-main">

        {/* Header */}
        <div className="page-header">
          <div>
            <div className="page-title">MEMORY BANK <span>// MOD-003-MEM</span></div>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', marginTop: 2 }}>
              EPISODIC LOG · SEMANTIC SEARCH · CONSOLIDATION STATUS
            </div>
          </div>
          {error && <span className="chip chip-amber">⚠ BACKEND OFFLINE</span>}
        </div>

        {/* Stat chips */}
        <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
          <div className="metric-card" style={{ flex: 1, minWidth: 140 }}>
            <div className="metric-label">EPISODIC RECORDS</div>
            <div className="metric-value">{count.toLocaleString()}</div>
            <div className="metric-sub">TOTAL EVENTS STORED</div>
          </div>
          <div className="metric-card" style={{ flex: 1, minWidth: 140 }}>
            <div className="metric-label">EVENT TYPES</div>
            <div className="metric-value" style={{ color: 'var(--on-surface)', fontSize: 20 }}>{types.length}</div>
            <div className="metric-sub truncate">{types.map(t => t?.toUpperCase()).join(' · ')}</div>
          </div>
          <div className="metric-card" style={{ flex: 1, minWidth: 140 }}>
            <div className="metric-label">STATUS</div>
            <div className="metric-value" style={{ fontSize: 14, color: 'var(--cyan)', marginTop: 4 }}>{error ? 'DEGRADED' : 'NOMINAL'}</div>
            <div className="metric-sub">SQLITE BACKEND</div>
          </div>
          <div className="metric-card" style={{ flex: 1, minWidth: 140 }}>
            <div className="metric-label">LAST EVENT</div>
            <div className="metric-value" style={{ fontSize: 13, color: 'var(--on-muted)', marginTop: 4 }}>{events[0] ? formatTs(events[0].timestamp) : '—'}</div>
            <div className="metric-sub">MOST RECENT</div>
          </div>
        </div>

        <div className="hud-grid-2" style={{ alignItems: 'flex-start' }}>

          {/* Episodic Log */}
          <div className="module" style={{ padding: 0 }}>
            <div className="corner-tl" /><div className="corner-br" />
            <div className="module-header">
              <span>EPISODIC MEMORY LOG</span>
              <span className="mod-id">MOD-003-EPS</span>
            </div>
            <div style={{ overflowY: 'auto', maxHeight: 500 }}>
              {loading && <div className="loading-text" style={{ padding: 24, textAlign: 'center' }}>LOADING MEMORY...</div>}
              {!loading && filtered.length === 0 && (
                <div style={{ padding: 24, textAlign: 'center', fontFamily: 'var(--font-label)', fontSize: 10, color: 'var(--outline)' }}>
                  {error ? 'NO DATA — BACKEND OFFLINE' : 'NO EVENTS FOUND'}
                </div>
              )}
              <table className="data-table">
                <thead>
                  <tr>
                    <th>TIMESTAMP</th>
                    <th>TYPE</th>
                    <th>SUMMARY</th>
                    <th>IMP</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((ev, i) => (
                    <tr key={i}>
                      <td style={{ whiteSpace: 'nowrap', fontSize: 10 }}>{formatTs(ev.timestamp)}</td>
                      <td>
                        <span className={`chip ${TYPE_COLOR[ev.event_type] ?? 'chip-muted'}`} style={{ fontSize: 8 }}>
                          {ev.event_type?.toUpperCase().replace('_', ' ')}
                        </span>
                      </td>
                      <td style={{ fontSize: 11, maxWidth: 200 }} className="truncate">{ev.content}</td>
                      <td style={{ color: IMP_COLOR[ev.importance ?? ''] ?? 'var(--outline)', fontFamily: 'var(--font-label)', fontSize: 9 }}>
                        {ev.importance ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Right column: Topology + Search */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Topology */}
            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>MEMORY TOPOLOGY</span><span className="mod-id">MOD-003-TOP</span></div>
              <div style={{ padding: 16 }}>
                <MemoryTopology types={types} />
              </div>
            </div>

            {/* Semantic Search */}
            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>SEMANTIC SEARCH</span><span className="mod-id">MOD-003-SRC</span></div>
              <div style={{ padding: 16 }}>
                <input
                  className="input-hud"
                  placeholder="QUERY MEMORY..."
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                />
                <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {['interaction', 'action', 'system', 'council_session'].map(t => (
                    <button key={t} onClick={() => setQuery(query === t ? '' : t)}
                      className={`chip ${query === t ? 'chip-cyan' : 'chip-muted'}`}
                      style={{ cursor: 'pointer', border: '1px solid', fontSize: 9 }}>
                      {t.toUpperCase().replace('_', ' ')}
                    </button>
                  ))}
                </div>
                <div style={{ marginTop: 12, fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)' }}>
                  {filtered.length} RESULTS
                </div>
              </div>
            </div>

            {/* Consolidation banner */}
            <div style={{ border: '1px solid var(--outline-dim)', padding: '10px 14px', fontFamily: 'var(--font-label)', fontSize: 9, display: 'flex', justifyContent: 'space-between', color: 'var(--on-muted)' }}>
              <span>CONSOLIDATION STATUS</span>
              <span className="chip chip-muted">AUTO · SCHEDULED</span>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}

function MemoryTopology({ types }: { types: string[] }) {
  const nodes = [
    { label: 'INTERACTIONS', x: 80,  y: 40,  hot: types.includes('interaction') },
    { label: 'ACTIONS',      x: 180, y: 40,  hot: types.includes('action') },
    { label: 'SYSTEM',       x: 130, y: 110, hot: types.includes('system') },
    { label: 'COUNCIL',      x: 50,  y: 130, hot: types.includes('council_session') },
    { label: 'SECURITY',     x: 210, y: 130, hot: types.includes('security_scan') },
  ];
  const links = [[0,2],[1,2],[2,3],[2,4],[0,1]];
  return (
    <svg width="100%" viewBox="0 0 260 170" style={{ overflow: 'visible' }}>
      {links.map(([a,b], i) => (
        <line key={i}
          x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y}
          stroke="rgba(59,130,246,0.3)" strokeWidth={1} />
      ))}
      {nodes.map((n, i) => (
        <g key={i}>
          <circle cx={n.x} cy={n.y} r={14} fill={n.hot ? 'rgba(0,255,255,0.15)' : 'rgba(58,74,73,0.4)'} stroke={n.hot ? 'var(--cyan)' : 'var(--outline-dim)'} strokeWidth={1.5} />
          <text x={n.x} y={n.y + 3} textAnchor="middle" fill={n.hot ? 'var(--cyan)' : 'var(--outline)'} fontSize={5} fontFamily="'Space Mono',monospace">
            {n.label}
          </text>
        </g>
      ))}
    </svg>
  );
}
