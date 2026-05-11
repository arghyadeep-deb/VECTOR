'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/hud/Sidebar';
import { api, type GoalsResponse } from '@/lib/api';

interface GoalNode { id: string; label: string; status: 'COMPLETE'|'IN_PROGRESS'|'PENDING'; progress: number; children?: GoalNode[]; }

const LONG_TERM: GoalNode = {
  id: 'root', label: 'Become a fully autonomous AI assistant', status: 'IN_PROGRESS', progress: 42,
  children: [
    { id: 'v', label: 'Complete Phase 3 Voice Pipeline', status: 'IN_PROGRESS', progress: 65,
      children: [
        { id: 'v1', label: 'Integrate Whisper STT', status: 'COMPLETE', progress: 100 },
        { id: 'v2', label: 'Integrate Kokoro TTS', status: 'IN_PROGRESS', progress: 80 },
        { id: 'v3', label: 'Wake word detection', status: 'PENDING', progress: 10 },
      ]
    },
    { id: 'm', label: 'Optimize Memory Consolidation', status: 'IN_PROGRESS', progress: 55,
      children: [
        { id: 'm1', label: 'Episodic log compression', status: 'COMPLETE', progress: 100 },
        { id: 'm2', label: 'Semantic indexing', status: 'IN_PROGRESS', progress: 40 },
      ]
    },
    { id: 'r', label: 'Expand Web Research Capability', status: 'PENDING', progress: 20,
      children: [
        { id: 'r1', label: 'Multi-source aggregator', status: 'IN_PROGRESS', progress: 35 },
        { id: 'r2', label: 'Fact verification chain', status: 'PENDING', progress: 0 },
      ]
    },
  ],
};

const NODE_COLOR: Record<string, string> = {
  COMPLETE: 'var(--cyan)', IN_PROGRESS: 'var(--cyan)', PENDING: 'var(--outline)',
};
const NODE_BG: Record<string, string> = {
  COMPLETE: 'rgba(0,255,255,0.2)', IN_PROGRESS: 'rgba(0,255,255,0.07)', PENDING: 'rgba(58,74,73,0.4)',
};
const DISTRICTS = [
  { label: 'RESEARCH',  agents: 3, glow: 0.9 },
  { label: 'MEMORY',    agents: 2, glow: 0.7 },
  { label: 'SECURITY',  agents: 2, glow: 0.5 },
  { label: 'INFERENCE', agents: 4, glow: 1.0 },
  { label: 'VOICE',     agents: 1, glow: 0.4 },
  { label: 'SENSING',   agents: 1, glow: 0.3 },
];

export default function GoalsPage() {
  const [goals, setGoals]   = useState<GoalsResponse | null>(null);
  const [error, setError]   = useState('');

  const load = useCallback(async () => {
    try { const d = await api.memoryGoals(); setGoals(d); setError(''); }
    catch (e: unknown) { setError((e as Error).message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const actions = goals?.immediate_actions ?? [];

  return (
    <div className="hud-layout">
      <Sidebar />
      <main className="hud-main">

        <div className="page-header">
          <div>
            <div className="page-title">GOALS & DISTRICTS <span>// MOD-004-GLS</span></div>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', marginTop: 2 }}>
              HIERARCHICAL GOAL TREE · PRIORITY QUEUE · CITY DISTRICT MAP
            </div>
          </div>
          {error && <span className="chip chip-amber">⚠ BACKEND OFFLINE</span>}
        </div>

        {/* Goal Tree */}
        <div className="module" style={{ padding: 0 }}>
          <div className="corner-tl" /><div className="corner-br" />
          <div className="module-header"><span>ACTIVE GOAL TREE</span><span className="mod-id">MOD-004-GLS</span></div>
          <div style={{ padding: 20, overflowX: 'auto' }}>
            <GoalTreeSVG />
          </div>
        </div>

        <div className="hud-grid-2" style={{ alignItems: 'flex-start' }}>

          {/* Goal queue */}
          <div className="module" style={{ padding: 0 }}>
            <div className="corner-tl" /><div className="corner-br" />
            <div className="module-header"><span>GOAL QUEUE</span><span className="mod-id">MOD-004-QUE</span></div>
            <div style={{ padding: 12 }}>
              {actions.length === 0 ? (
                /* Static fallback goals */
                [
                  { p: 'P1', label: 'Finalize voice pipeline integration', agent: 'Orchestrator', eta: '2h 15m', status: 'IN_PROGRESS' },
                  { p: 'P1', label: 'Consolidate episodic memory backlog', agent: 'Memory Curator', eta: '45m', status: 'PENDING' },
                  { p: 'P2', label: 'Run web research on AI safety news', agent: 'Researcher', eta: '1h', status: 'PENDING' },
                  { p: 'P2', label: 'Verify malware scan completion', agent: 'Security Sentinel', eta: '10m', status: 'ACTIVE' },
                  { p: 'P3', label: 'Update training data from council sessions', agent: 'Pattern Finder', eta: '3h', status: 'PENDING' },
                  { p: 'P3', label: 'Optimize Ollama model routing weights', agent: 'Orchestrator', eta: '4h', status: 'BLOCKED' },
                ].map((g, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, padding: '9px 4px', borderBottom: i < 5 ? '1px solid var(--outline-dim)' : 'none', alignItems: 'center' }}>
                    <span className={`chip ${g.p === 'P1' ? 'chip-cyan' : g.p === 'P2' ? 'chip-blue' : 'chip-muted'}`} style={{ fontSize: 8 }}>{g.p}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: g.status === 'BLOCKED' ? 'var(--amber)' : 'var(--on-surface)' }}>{g.label}</div>
                      <div style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--on-muted)', marginTop: 2 }}>{g.agent}</div>
                    </div>
                    <span className="chip chip-muted" style={{ fontSize: 8, whiteSpace: 'nowrap' }}>{g.eta}</span>
                  </div>
                ))
              ) : actions.map((a, i) => (
                <div key={i} style={{ padding: '8px 4px', borderBottom: '1px solid var(--outline-dim)', fontFamily: 'var(--font-body)', fontSize: 12 }}>
                  {String(a.action ?? a.description ?? JSON.stringify(a)).slice(0, 70)}
                </div>
              ))}
            </div>
          </div>

          {/* City district map */}
          <div className="module" style={{ padding: 0 }}>
            <div className="corner-tl" /><div className="corner-br" />
            <div className="module-header"><span>CITY DISTRICT MAP</span><span className="mod-id">MOD-007-CTY</span></div>
            <div style={{ padding: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                {DISTRICTS.map(d => (
                  <div key={d.label} style={{
                    padding: '14px 10px',
                    border: `1px solid rgba(0,255,255,${d.glow * 0.4})`,
                    background: `rgba(0,255,255,${d.glow * 0.04})`,
                    boxShadow: `0 0 ${d.glow * 12}px rgba(0,255,255,${d.glow * 0.1})`,
                    display: 'flex', flexDirection: 'column', gap: 4,
                  }}>
                    <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: `rgba(0,255,255,${0.4 + d.glow * 0.6})`, letterSpacing: '0.1em' }}>{d.label}</div>
                    <div style={{ fontFamily: 'var(--font-data)', fontSize: 18, color: `rgba(0,255,255,${0.5 + d.glow * 0.5})` }}>{d.agents}</div>
                    <div style={{ fontFamily: 'var(--font-label)', fontSize: 7, color: 'var(--outline)' }}>AGENTS</div>
                    <div className="progress-track" style={{ marginTop: 4 }}>
                      <div className="progress-fill" style={{ width: `${d.glow * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}

function GoalTreeSVG() {
  // Manual layout for the tree
  const W = 900; const H = 220;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ minWidth: 600 }}>
      {/* Root */}
      <GoalNodeRect x={350} y={10} w={200} h={40} node={LONG_TERM} />
      {/* Mid-level */}
      {LONG_TERM.children!.map((child, ci) => {
        const cx = 120 + ci * 280; const cy = 90;
        return (
          <g key={child.id}>
            <line x1={450} y1={50} x2={cx + 100} y2={cy} stroke="rgba(0,255,255,0.2)" strokeWidth={1} strokeDasharray="4 3" />
            <GoalNodeRect x={cx} y={cy} w={200} h={38} node={child} />
            {child.children?.map((sub, si) => {
              const sx = cx + (si - (child.children!.length - 1) / 2) * 70; const sy = 165;
              return (
                <g key={sub.id}>
                  <line x1={cx + 100} y1={cy + 38} x2={sx} y2={sy} stroke="rgba(59,130,246,0.25)" strokeWidth={1} />
                  <rect x={sx - 32} y={sy} width={64} height={20} fill={NODE_BG[sub.status]} stroke={NODE_COLOR[sub.status]} strokeWidth={0.8} strokeOpacity={0.5} />
                  <text x={sx} y={sy + 7} textAnchor="middle" fill={NODE_COLOR[sub.status]} fontSize={5.5} fontFamily="'Space Mono',monospace"
                    opacity={sub.status === 'PENDING' ? 0.5 : 1}>
                    {sub.label.slice(0, 14)}
                  </text>
                  <rect x={sx - 32} y={sy + 14} width={64 * sub.progress / 100} height={3} fill={NODE_COLOR[sub.status]} opacity={0.6} />
                  <text x={sx + 34} y={sy + 10} fill={NODE_COLOR[sub.status]} fontSize={5} fontFamily="'JetBrains Mono',monospace" opacity={0.7}>{sub.progress}%</text>
                </g>
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}

function GoalNodeRect({ x, y, w, h, node }: { x: number; y: number; w: number; h: number; node: GoalNode }) {
  const col = NODE_COLOR[node.status];
  const bg  = NODE_BG[node.status];
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} fill={bg} stroke={col} strokeWidth={1.5} filter={node.status === 'IN_PROGRESS' ? `drop-shadow(0 0 6px ${col})` : undefined} />
      <text x={x + w / 2} y={y + 11} textAnchor="middle" fill={col} fontSize={7} fontFamily="'Space Mono',monospace" fontWeight="700">
        {node.status === 'IN_PROGRESS' ? '▶' : node.status === 'COMPLETE' ? '✓' : '○'} {node.status}
      </text>
      <text x={x + w / 2} y={y + 22} textAnchor="middle" fill="var(--on-surface)" fontSize={6.5} fontFamily="'Inter',sans-serif">
        {node.label.slice(0, 28)}
      </text>
      <rect x={x + 8} y={y + h - 6} width={(w - 16) * node.progress / 100} height={2} fill={col} opacity={0.7} />
      <text x={x + w - 4} y={y + h - 4} textAnchor="end" fill={col} fontSize={5} fontFamily="'JetBrains Mono',monospace">{node.progress}%</text>
    </g>
  );
}
