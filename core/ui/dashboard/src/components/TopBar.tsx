import { useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { formatUptime } from '../lib/api'
import { Z } from '../lib/zIndex'

const bar: React.CSSProperties = {
  position: 'fixed', top: 0, left: 0, right: 0, height: 40, zIndex: Z.TOP_BAR,
  display: 'flex', alignItems: 'center', padding: '0 16px',
  borderBottom: '1px solid rgba(0,212,255,0.12)',
  background: 'rgba(5,13,26,0.95)',
  backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
  clipPath: 'polygon(12px 0%, 100% 0%, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0% 100%, 0% 12px)',
}

export default function TopBar() {
  const status = useVectorStore((s) => s.status)
  const [time, setTime] = useState(new Date())
  const [initial, setInitial] = useState(true)

  useEffect(() => { const t = setTimeout(() => setInitial(false), 5000); return () => clearTimeout(t) }, [])
  useEffect(() => { const id = setInterval(() => setTime(new Date()), 1000); return () => clearInterval(id) }, [])

  const statusText = !status && initial ? 'CONNECTING' : !status ? 'OFFLINE' : status?.loop_running ? 'ONLINE' : 'DEGRADED'
  const statusColor = !status && initial ? '#FFB300' : !status ? '#2a2a2a' : status?.loop_running ? '#00FF88' : '#FF3D3D'
  const ts = time.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })

  return (
    <div role="banner" style={bar}>
      {/* Logo */}
      <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 15, fontWeight: 700, color: '#00d4ff', letterSpacing: '0.15em', display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <polygon points="12,2 22,20 2,20" fill="none" stroke="#00d4ff" strokeWidth="1.5" strokeLinejoin="round" />
          <circle cx="12" cy="14" r="3.5" fill="none" stroke="#00d4ff" strokeWidth="1" />
          <line x1="12" y1="2" x2="12" y2="8" stroke="#00d4ff" strokeWidth="1" opacity="0.5" />
        </svg>
        VECTOR
      </div>

      <div style={{ width: 1, height: 20, background: 'rgba(0,212,255,0.12)', margin: '0 12px' }} />

      {/* Status stats */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.12em', textTransform: 'uppercase' }}>Status</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: statusColor, display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 4, height: 4, borderRadius: '50%', background: statusColor, animation: statusText === 'ONLINE' ? 'v-pulse 1.5s infinite' : 'none' }} />
            {statusText}
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.12em', textTransform: 'uppercase' }}>Uptime</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>{status ? formatUptime(status.uptime_seconds) : '—'}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.12em', textTransform: 'uppercase' }}>Agents</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>{status?.agents?.count?.toString() ?? '—'}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.12em', textTransform: 'uppercase' }}>Memory</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>{status?.memory?.episodic_memory?.toString() ?? '—'} ev</span>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Clock */}
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#00d4ff', letterSpacing: '0.1em', textShadow: '0 0 12px rgba(0,212,255,0.3)' }}>
        {ts}
      </div>
    </div>
  )
}
