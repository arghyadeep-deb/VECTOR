import { useVectorStore } from '../store/vectorStore'

interface JupyterData {
  active_sessions: number
  sessions_path: string
}

export default function JupyterPanel() {
  const d = useVectorStore((s) => (s as any).jupyter) as JupyterData | undefined

  return (
    <div style={{
      width: '100%', zIndex: 40, background: 'rgba(5,13,26,0.88)',
      backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
      border: '1px solid rgba(0,212,255,0.08)',
      boxShadow: '0 0 30px rgba(0,212,255,0.04), inset 0 0 30px rgba(0,212,255,0.02)',
      paddingBottom: 4,
    }}>
      <div style={{
        fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688',
        letterSpacing: '0.15em', padding: '6px 10px 4px',
        borderBottom: '1px solid rgba(0,207,255,0.06)',
      }}>
        HARNESS
      </div>

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)',
      }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#3388aa', letterSpacing: '0.1em' }}>ACTIVE SESSIONS</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>
          {d ? d.active_sessions : '—'}
        </span>
      </div>

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 10px',
      }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#3388aa', letterSpacing: '0.1em' }}>SESSIONS PATH</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 8, color: '#6a9abf', maxWidth: 130, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {d?.sessions_path ?? '—'}
        </span>
      </div>
    </div>
  )
}
