'use client';
import { useEffect, useState, useCallback } from 'react';
import Sidebar from '@/components/hud/Sidebar';
import { api, formatTs, type MemoryEvent, type HealthResponse } from '@/lib/api';

const MOCK_SCAN = [
  { ts: '14:02:11', type: 'REAL_TIME', target: '/sys/bin/vector-core', result: 'CLEAN' },
  { ts: '14:01:45', type: 'HEURISTIC', target: '/usr/local/ollama/bin', result: 'CLEAN' },
  { ts: '13:58:30', type: 'DEEP_PKT',  target: '/tmp/0x4f2a.sock',      result: 'SUSPICIOUS' },
  { ts: '13:55:10', type: 'REAL_TIME', target: '/home/user/.vector/db',  result: 'CLEAN' },
  { ts: '13:50:00', type: 'HEURISTIC', target: '/etc/vector/config.yml', result: 'CLEAN' },
];
const MOCK_PERMS = [
  { agent: 'Researcher',       action: 'NET_OUT',   risk: 'LOW',  status: 'APPROVED' },
  { agent: 'Orchestrator',     action: 'FS_RENAME',  risk: 'MED',  status: 'APPROVED' },
  { agent: 'Security Sentinel',action: 'MEM_W_0',    risk: 'CRIT', status: 'DENIED'   },
  { agent: 'Voice Processor',  action: 'NET_OUT',   risk: 'LOW',  status: 'APPROVED' },
  { agent: 'Pattern Finder',   action: 'FS_READ',   risk: 'LOW',  status: 'PENDING'  },
];

export default function SecurityPage() {
  const [events,    setEvents]  = useState<MemoryEvent[]>([]);
  const [secStatus, setSecStatus] = useState<any>(null);
  const [health,    setHealth]  = useState<HealthResponse | null>(null);
  const [error,     setError]   = useState('');

  const load = useCallback(async () => {
    try {
      const [e, h, s] = await Promise.all([
        api.securityRecent(15),
        api.health(),
        api.securityStatus()
      ]);
      setEvents(e.events ?? []);
      setHealth(h);
      setSecStatus(s);
      setError('');
    } catch (err: unknown) { setError((err as Error).message); }
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 12000); return () => clearInterval(id); }, [load]);

  const suspicious = secStatus?.anomalies_found ?? events.filter(e => e.tags?.includes('suspicious')).length;
  const threatLevel = (secStatus?.threat_level ?? 'low').toUpperCase();
  const threatColor = threatLevel === 'HIGH' ? 'chip-red' : threatLevel === 'MEDIUM' ? 'chip-amber' : 'chip-cyan';

  const scans = events.length > 0
    ? events.map(e => ({
        ts: formatTs(e.timestamp),
        type: (e.context?.scan_type as string ?? 'REAL_TIME').toUpperCase(),
        target: (e.context?.target as string ?? e.content?.slice(0, 30) ?? '—'),
        result: (e.tags?.includes('suspicious') ? 'SUSPICIOUS' : 'CLEAN'),
      }))
    : MOCK_SCAN;

  return (
    <div className="hud-layout">
      <Sidebar />
      <main className="hud-main">

        {/* Header */}
        <div className="page-header">
          <div>
            <div className="page-title">SECURITY MONITOR <span>// MOD-006-SEC</span></div>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', marginTop: 2 }}>
              MALWARE DETECTION · PERMISSION GATEWAY · SANDBOX TELEMETRY
            </div>
          </div>
          {error && <span className="chip chip-amber">⚠ BACKEND OFFLINE</span>}
        </div>

        {/* Status chips */}
        <div className="flex gap-3" style={{ flexWrap: 'wrap' }}>
          {[
            { label: 'THREAT LEVEL',     value: threatLevel,         cls: threatColor },
            { label: 'ACTIVE SCANS',     value: '3 RUNNING',         cls: 'chip-cyan' },
            { label: 'ANOMALIES',        value: `${suspicious} FOUND`, cls: suspicious > 0 ? 'chip-amber' : 'chip-cyan' },
            { label: 'SANDBOX',          value: 'ACTIVE',            cls: 'chip-amber' },
            { label: 'BACKEND HEALTH',   value: health?.status?.toUpperCase() ?? 'UNKNOWN', cls: health?.status === 'ok' ? 'chip-cyan' : 'chip-amber' },
          ].map(({ label, value, cls }) => (
            <div key={label} className="metric-card" style={{ minWidth: 150, flex: 1 }}>
              <div className="metric-label">{label}</div>
              <div style={{ marginTop: 6 }}><span className={`chip ${cls}`} style={{ fontSize: 11 }}>{value}</span></div>
            </div>
          ))}
        </div>

        <div className="hud-grid-2" style={{ alignItems: 'flex-start' }}>

          {/* Malware feed */}
          <div className="module" style={{ padding: 0 }}>
            <div className="corner-tl" /><div className="corner-br" />
            <div className="module-header"><span>MALWARE DETECTION FEED</span><span className="mod-id">MOD-006-MLW</span></div>
            <div style={{ overflowY: 'auto', maxHeight: 380 }}>
              <table className="data-table">
                <thead>
                  <tr><th>TIME</th><th>SCAN TYPE</th><th>TARGET</th><th>RESULT</th></tr>
                </thead>
                <tbody>
                  {scans.map((s, i) => (
                    <tr key={i} style={{ background: s.result === 'SUSPICIOUS' ? 'rgba(255,191,0,0.04)' : undefined }}>
                      <td style={{ fontSize: 10, whiteSpace: 'nowrap' }}>{s.ts}</td>
                      <td><span className="chip chip-blue" style={{ fontSize: 8 }}>{s.type}</span></td>
                      <td style={{ fontSize: 10, maxWidth: 160 }} className="truncate">{s.target}</td>
                      <td>
                        {s.result === 'SUSPICIOUS'
                          ? <span className="chip chip-amber blink" style={{ fontSize: 8 }}>⚠ SUSPICIOUS</span>
                          : <span className="chip chip-cyan" style={{ fontSize: 8 }}>✓ CLEAN</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Permission gateway + sandbox */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>PERMISSION GATEWAY</span><span className="mod-id">MOD-006-PRM</span></div>
              <table className="data-table">
                <thead><tr><th>AGENT</th><th>ACTION</th><th>RISK</th><th>STATUS</th></tr></thead>
                <tbody>
                  {(secStatus?.audit_log?.length > 0 ? secStatus.audit_log : MOCK_PERMS).map((p: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontSize: 11 }}>{p.proposed_by ?? p.agent}</td>
                      <td style={{ fontFamily: 'var(--font-data)', fontSize: 10 }}>{p.action_type ?? p.action}</td>
                      <td>
                        <span className={`chip ${p.level === 'RED' || p.risk === 'CRIT' ? 'chip-red' : p.level === 'YELLOW' || p.risk === 'MED' ? 'chip-amber' : 'chip-cyan'}`} style={{ fontSize: 8 }}>
                          {p.level ?? p.risk}
                        </span>
                      </td>
                      <td>
                        <span className={`chip ${p.approved ? 'chip-cyan' : p.status === 'DENIED' ? 'chip-red' : 'chip-amber'}`} style={{ fontSize: 8 }}>
                          {p.approved ? 'APPROVED' : p.status ?? 'PENDING'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Sandboxed processes */}
            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>SANDBOXED PROCESSES</span><span className="mod-id">MOD-006-SBX</span></div>
              <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(secStatus?.processes?.length > 0 ? secStatus.processes : [
                  { name: 'ollama-serve',   cpu: 42, mem: 68 },
                  { name: 'whisper-worker', cpu: 18, mem: 35 },
                  { name: 'vector-core',    cpu: 7,  mem: 22 },
                ]).map((p: any) => (
                  <div key={p.name} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div className="flex justify-between">
                      <span style={{ fontFamily: 'var(--font-data)', fontSize: 11 }}>{p.name}</span>
                      <span style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--on-muted)' }}>CPU {Math.round(p.cpu)}% · MEM {Math.round(p.mem)}%</span>
                    </div>
                    <div className="progress-track">
                      <div className="progress-fill" style={{ width: `${p.cpu}%`, background: p.cpu > 60 ? 'var(--amber)' : 'var(--cyan)' }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Health checks */}
            {health && (
              <div className="module" style={{ padding: 0 }}>
                <div className="corner-tl" /><div className="corner-br" />
                <div className="module-header"><span>SYSTEM HEALTH</span><span className="mod-id">MOD-006-HLT</span></div>
                <div style={{ padding: 12 }}>
                  {Object.entries(health.checks).map(([k, v]) => (
                    <div key={k} className="flex justify-between items-center" style={{ padding: '5px 4px', borderBottom: '1px solid var(--outline-dim)' }}>
                      <span style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', letterSpacing: '0.1em' }}>{k.toUpperCase()}</span>
                      <span className={`chip ${v === 'ok' ? 'chip-cyan' : 'chip-amber'}`} style={{ fontSize: 8 }}>{v.toUpperCase()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Security policy banner */}
        <div style={{ border: '1px solid var(--outline-dim)', padding: '10px 16px', fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <span>SECURITY POLICY</span>
          <span>PARANOID_MODE: <span style={{ color: 'var(--cyan)' }}>OFF</span></span>
          <span>AUTO_APPROVE_THRESHOLD: <span style={{ color: 'var(--cyan)' }}>LOW_RISK</span></span>
          <span>HUMAN_IN_LOOP: <span style={{ color: 'var(--cyan)' }}>ENABLED</span></span>
          <span>LOCAL_ONLY: <span style={{ color: 'var(--cyan)' }}>ENFORCED</span></span>
        </div>

      </main>
    </div>
  );
}
