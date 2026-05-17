import { VectorState } from '../App'

interface Props { state: VectorState }

export function StatusBar({ state }: Props) {
  const now = new Date()
  const time = now.toLocaleTimeString('en-IN', { hour12: false })
  const date = now.toLocaleDateString('en-IN', { weekday: 'short', month: 'short', day: 'numeric' })

  return (
    <div style={{
      height: '100%',
      background: 'var(--jarvis-surface)',
      borderTop: '1px solid var(--jarvis-border)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 12px',
      fontSize: '0.6rem',
      letterSpacing: '0.1em',
      color: 'var(--jarvis-text-dim)',
    }}>
      <div style={{ display: 'flex', gap: 16 }}>
        <span>VECTOR v1.0 · PHASE 1</span>
        <span>DISTRICT: <span style={{ color: 'var(--jarvis-cyan)' }}>{state.district.toUpperCase()}</span></span>
        <span>AGENTS: <span style={{ color: '#30FF6A' }}>{state.activeAgents}</span></span>
      </div>
      <div style={{ color: 'var(--jarvis-text-muted)' }}>
        ARGHYADEEP DEB · KIIT CSE · LEGION PRO 5 · RTX 5070 Ti
      </div>
      <div style={{ display: 'flex', gap: 16 }}>
        <span style={{ color: 'var(--jarvis-cyan)' }}>{time}</span>
        <span>{date}</span>
        <span>IST</span>
      </div>
    </div>
  )
}
