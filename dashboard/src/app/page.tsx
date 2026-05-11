'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/hud/Sidebar';
import { api, formatUptime, formatTs, modelColor, type StatusResponse, type MemoryEvent } from '@/lib/api';

export default function MainHUD() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [events, setEvents] = useState<MemoryEvent[]>([]);
  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([api.status(), api.memoryRecent(10)]);
      setStatus(s);
      setEvents(m.events);
      setError('');
    } catch (e: unknown) {
      setError((e as Error).message ?? 'Brain server unreachable');
    }
  }, []);

  useEffect(() => { load(); const id = setInterval(() => { load(); setTick(t => t + 1); }, 5000); return () => clearInterval(id); }, [load]);

  const memUsage = typeof status?.memory?.episodic_count === 'number'
    ? Math.min(99, Math.round((status.memory.episodic_count as number) / 100))
    : 0;

  return (
    <div className="hud-layout">
      <Sidebar />
      <main className="hud-main">

        {/* Header */}
        <div className="page-header">
          <div>
            <div className="page-title">MAIN HUD <span>// MOD-001-SYS</span></div>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', marginTop: 2 }}>
              COGNITIVE LOAD MONITOR · SYSTEM TELEMETRY · REAL-TIME FEED
            </div>
          </div>
          <div className="flex items-center gap-2">
            {error
              ? <span className="chip chip-red">● OFFLINE</span>
              : <span className="chip chip-cyan">● ONLINE</span>}
            <span className="chip chip-muted text-data" style={{ fontSize: 9 }}>
              TICK {tick.toString().padStart(4, '0')}
            </span>
          </div>
        </div>

        {error && (
          <div style={{ padding: '10px 14px', border: '1px solid rgba(255,68,68,0.4)', background: 'rgba(255,68,68,0.07)', fontFamily: 'var(--font-label)', fontSize: 10, color: 'var(--red)', letterSpacing: '0.1em' }}>
            ⚠ {error.toUpperCase()} — RETRYING IN 5s
          </div>
        )}

        {/* Metric row */}
        <div className="hud-grid-4">
          {[
            { label: 'SYSTEM STATUS',   value: status ? (status.loop_running ? 'ONLINE' : 'IDLE') : '—',       sub: 'LOOP ACTIVE',                        cyan: true },
            { label: 'UPTIME',          value: status ? formatUptime(status.uptime_seconds) : '—',              sub: `v${status?.vector_version ?? '—'}`,   cyan: false },
            { label: 'ACTIVE AGENTS',   value: status?.agents.count?.toString() ?? '—',                         sub: (status?.agents.districts ?? []).join(' · ') || '—', cyan: false },
            { label: 'MEMORY EVENTS',   value: typeof status?.memory?.episodic_count === 'number' ? (status.memory.episodic_count as number).toLocaleString() : '—', sub: 'EPISODIC RECORDS', cyan: false },
          ].map(({ label, value, sub, cyan }) => (
            <div key={label} className="metric-card animate-in">
              <div className="metric-label">{label}</div>
              <div className="metric-value" style={cyan ? undefined : { color: 'var(--on-surface)', fontSize: 20 }}>{value}</div>
              <div className="metric-sub truncate">{sub}</div>
            </div>
          ))}
        </div>

        {/* Body: Cognitive Load + Models + Feed */}
        <div className="hud-row" style={{ gap: 16, alignItems: 'flex-start' }}>

          {/* Left: Cognitive Dial + Districts */}
          <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>COGNITIVE LOAD</span><span className="mod-id">MOD-001-CGL</span></div>
              <div style={{ padding: 24, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
                <CognitiveDial value={memUsage} />
                <div className="font-label" style={{ fontSize: 9, color: 'var(--on-muted)', textAlign: 'center' }}>
                  MEMORY UTILISATION INDEX
                </div>
              </div>
            </div>

            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>AI MODELS</span><span className="mod-id">MOD-001-MDL</span></div>
              <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {status?.models
                  ? Object.entries(status.models).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between" style={{ padding: '5px 4px' }}>
                      <span style={{ fontFamily: 'var(--font-data)', fontSize: 11, color: 'var(--on-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{k}</span>
                      <span className={`chip ${modelColor(v)}`} style={{ fontSize: 8 }}>{v.toUpperCase()}</span>
                    </div>
                  ))
                  : <span className="loading-text">QUERYING MODELS...</span>}
              </div>
            </div>
          </div>

          {/* Center: Recent Event Feed */}
          <div className="module flex-1" style={{ padding: 0 }}>
            <div className="corner-tl" /><div className="corner-br" />
            <div className="module-header">
              <span>LIVE MEMORY FEED</span>
              <span className="mod-id">MOD-001-MEM</span>
            </div>
            <div style={{ padding: 12, maxHeight: 440, overflowY: 'auto' }}>
              {events.length === 0
                ? <div className="loading-text" style={{ padding: '20px 0', textAlign: 'center' }}>AWAITING EVENTS...</div>
                : events.map((ev, i) => (
                  <div key={i} className="event-row animate-in">
                    <div className="event-time">{formatTs(ev.timestamp)}</div>
                    <div>
                      <span className={`chip chip-muted`} style={{ fontSize: 8, marginBottom: 3 }}>{ev.event_type?.toUpperCase()}</span>
                      <div className="event-content" style={{ fontSize: 12 }}>{ev.content}</div>
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {/* Right: Districts */}
          <div style={{ width: 200, flexShrink: 0 }}>
            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>DISTRICTS</span><span className="mod-id">MOD-001-DST</span></div>
              <div style={{ padding: 10 }}>
                {(status?.agents.districts ?? ['research','memory','security','inference']).map((d, i) => (
                  <div key={d} className="flex items-center gap-2" style={{ padding: '7px 4px', borderBottom: i < (status?.agents.districts.length ?? 0) - 1 ? '1px solid var(--outline-dim)' : 'none' }}>
                    <span className="dot dot-cyan" style={{ width: 5, height: 5 }} />
                    <span style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-surface)', letterSpacing: '0.1em' }}>{d.toUpperCase()}</span>
                  </div>
                ))}
                {!status && <span className="loading-text">SCANNING...</span>}
              </div>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}

function CognitiveDial({ value }: { value: number }) {
  const r = 70; const cx = 80; const cy = 80;
  const circ = 2 * Math.PI * r;
  const pct = value / 100;
  const offset = circ * (1 - pct);
  const color = value > 80 ? '#ffbf00' : value > 60 ? '#00dddd' : '#00ffff';
  return (
    <svg width={160} height={160} viewBox="0 0 160 160">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--outline-dim)" strokeWidth={6} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={6}
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="butt" transform={`rotate(-90 ${cx} ${cy})`}
        style={{ transition: 'stroke-dashoffset 1s ease, stroke 0.5s' }}
        filter={`drop-shadow(0 0 8px ${color})`}
      />
      {/* Inner rings */}
      <circle cx={cx} cy={cy} r={54} fill="none" stroke="rgba(0,255,255,0.06)" strokeWidth={1} />
      <circle cx={cx} cy={cy} r={38} fill="none" stroke="rgba(0,255,255,0.04)" strokeWidth={1} />
      <text x={cx} y={cy - 6} textAnchor="middle" fill={color} fontSize={28} fontFamily="'JetBrains Mono',monospace" fontWeight="500">
        {value}
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle" fill="var(--on-muted)" fontSize={10} fontFamily="'Space Mono',monospace">
        %
      </text>
    </svg>
  );
}
