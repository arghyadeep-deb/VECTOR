'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/hud/Sidebar';
import { api, formatTs, type Agent } from '@/lib/api';

const ROLE_MAP: Record<string, string> = {
  research: 'RESEARCH', memory: 'MEMORY', security: 'SECURITY',
  inference: 'INFERENCE', voice: 'COMM', coordination: 'COORD',
};

const SPARKLINE_H = 24;
function Sparkline({ active }: { active: boolean }) {
  const pts = Array.from({ length: 16 }, () => active ? Math.random() * 18 + 4 : Math.random() * 4 + 1);
  const w = 80;
  const path = pts.map((p, i) => `${(i / (pts.length - 1)) * w},${SPARKLINE_H - p}`).join(' L ');
  return (
    <svg width={w} height={SPARKLINE_H} viewBox={`0 0 ${w} ${SPARKLINE_H}`} style={{ overflow: 'visible' }}>
      <polyline points={path} fill="none" stroke={active ? 'var(--cyan)' : 'var(--outline)'} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [count, setCount] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const d = await api.agents();
      setAgents(d.agents ?? []);
      setCount(d.count ?? 0);
      setError('');
    } catch (e: unknown) { setError((e as Error).message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 8000); return () => clearInterval(id); }, [load]);

  const active = agents.filter(a => a.status === 'active' || a.status === 'running');
  const idle   = agents.filter(a => a.status !== 'active' && a.status !== 'running');

  return (
    <div className="hud-layout">
      <Sidebar />
      <main className="hud-main">

        <div className="page-header">
          <div>
            <div className="page-title">AGENT REGISTRY <span>// MOD-002-AGT</span></div>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', marginTop: 2 }}>
              {count} AGENTS REGISTERED · {active.length} ACTIVE · {idle.length} IDLE
            </div>
          </div>
          <div className="flex items-center gap-2">
            {error && <span className="chip chip-amber">⚠ BACKEND OFFLINE</span>}
            <button className="btn btn-primary" onClick={load} style={{ fontSize: 9 }}>↺ REFRESH</button>
          </div>
        </div>

        {loading && (
          <div className="module" style={{ padding: 24, textAlign: 'center' }}>
            <div className="loading-text">SCANNING AGENT REGISTRY...</div>
          </div>
        )}

        {!loading && agents.length === 0 && (
          <div className="module" style={{ padding: 24, textAlign: 'center' }}>
            <div className="loading-text">
              {error ? `⚠ ${error.toUpperCase()}` : 'NO AGENTS REGISTERED'}
            </div>
            <div style={{ marginTop: 12, fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--on-muted)' }}>
              Start the V.E.C.T.O.R. brain server to see registered agents.
            </div>
          </div>
        )}

        {/* Active Agents */}
        {active.length > 0 && (
          <>
            <div className="font-label" style={{ fontSize: 9, color: 'var(--cyan-dim)', letterSpacing: '0.2em', paddingLeft: 2 }}>
              ● ACTIVE — {active.length} AGENTS
            </div>
            <div className="hud-grid-3">
              {active.map((a, i) => <AgentCard key={a.id ?? i} agent={a} active />)}
            </div>
          </>
        )}

        {/* Idle Agents */}
        {idle.length > 0 && (
          <>
            <div className="font-label" style={{ fontSize: 9, color: 'var(--on-muted)', letterSpacing: '0.2em', paddingLeft: 2 }}>
              ○ IDLE — {idle.length} AGENTS
            </div>
            <div className="hud-grid-3">
              {idle.map((a, i) => <AgentCard key={a.id ?? i} agent={a} active={false} />)}
            </div>
          </>
        )}

        {/* Fallback: show mock agents if offline */}
        {!loading && agents.length === 0 && error && (
          <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--outline)', textAlign: 'center', padding: '8px 0', letterSpacing: '0.15em' }}>
            SHOWING CACHED REGISTRY DATA UNAVAILABLE — CONNECT BRAIN SERVER
          </div>
        )}

      </main>
    </div>
  );
}

function AgentCard({ agent, active }: { agent: Agent; active: boolean }) {
  const district = agent.district ?? 'unknown';
  const role = ROLE_MAP[district] ?? district.toUpperCase().slice(0, 8);
  const hp = typeof agent.hp === 'number' ? agent.hp : null;

  return (
    <div className={`agent-card animate-in ${active ? 'active' : 'idle'}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`dot ${active ? 'dot-cyan' : 'dot-grey'}`} />
          <span className={`chip ${active ? 'chip-cyan' : 'chip-muted'}`} style={{ fontSize: 8 }}>
            AGT-{(agent.id ?? '000').toString().slice(-3).toUpperCase()}
          </span>
        </div>
        <span className="chip chip-blue" style={{ fontSize: 8 }}>{role}</span>
      </div>

      {/* Name */}
      <div>
        <div style={{ fontFamily: 'var(--font-head)', fontSize: 15, fontWeight: 600, color: active ? 'var(--on-surface)' : 'var(--on-muted)' }}>
          {(agent.name ?? agent.id ?? 'Unknown').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
        </div>
        <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', marginTop: 2 }}>
          {district.toUpperCase()} DISTRICT
        </div>
      </div>

      {/* Sparkline */}
      <div className="flex items-center justify-between">
        <Sparkline active={active} />
        {hp !== null && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--on-muted)' }}>HP</div>
            <div style={{ fontFamily: 'var(--font-data)', fontSize: 14, color: hp > 50 ? 'var(--cyan)' : 'var(--amber)' }}>{hp}</div>
          </div>
        )}
      </div>

      {/* Last action */}
      {agent.last_action && (
        <div style={{ fontFamily: 'var(--font-data)', fontSize: 10, color: 'var(--on-muted)', borderTop: '1px solid var(--outline-dim)', paddingTop: 8 }}>
          <span style={{ color: 'var(--outline)', marginRight: 4 }}>LAST:</span>
          <span className="truncate">{formatTs(agent.last_action as string)}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <button className="btn btn-ghost flex-1" style={{ fontSize: 8, padding: '5px 8px' }}>INSPECT</button>
        <button className="btn btn-ghost" style={{ fontSize: 8, padding: '5px 8px', color: active ? 'var(--amber)' : 'var(--cyan)', borderColor: active ? 'rgba(255,191,0,0.4)' : 'rgba(0,255,255,0.4)' }}>
          {active ? 'PAUSE' : 'RESUME'}
        </button>
      </div>
    </div>
  );
}
