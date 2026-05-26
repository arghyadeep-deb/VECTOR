import { useState, useEffect, useRef } from 'react'
import './index.css'
import { VectorCore } from './components/VectorCore'
import { AgentPanel } from './components/panels/AgentPanel'
import { ChatPanel } from './components/panels/ChatPanel'
import { StatusBar } from './components/StatusBar'
import { VectorMascot } from './components/VectorMascot'
import { SystemMetrics } from './components/panels/SystemMetrics'
import { DistrictMap } from './components/panels/DistrictMap'
import { ContentPanel } from './panels/ContentPanel'

export type AppStatus = 'offline' | 'connecting' | 'online' | 'thinking' | 'speaking'

export interface VectorState {
  status: AppStatus
  activeAgents: number
  totalTasks: number
  memoryUsage: number
  uptime: string
  lastAction: string
  district: string
}

const VECTOR_WS_URL = 'http://127.0.0.1:8000'

export default function App() {
  const [state, setState] = useState<VectorState>({
    status: 'connecting',
    activeAgents: 0,
    totalTasks: 0,
    memoryUsage: 0,
    uptime: '00:00:00',
    lastAction: 'Initializing systems...',
    district: 'governance',
  })
  const [messages, setMessages] = useState<Array<{ role: string; content: string; ts: string }>>([])
  const [input, setInput] = useState('')
  const [activePanel, setActivePanel] = useState<'chat' | 'agents' | 'metrics' | 'districts'>('chat')
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    connectToVector()
    const timer = setInterval(updateUptime, 1000)
    return () => {
      clearInterval(timer)
      wsRef.current?.close()
    }
  }, [])

  const connectToVector = () => {
    try {
      const ws = new WebSocket(`ws://127.0.0.1:8000/ws/state`)
      wsRef.current = ws
      ws.onopen = () => setState(s => ({ ...s, status: 'online' }))
      ws.onmessage = (e) => handleMessage(JSON.parse(e.data))
      ws.onclose = () => {
        setState(s => ({ ...s, status: 'offline' }))
        setTimeout(connectToVector, 5000)
      }
      ws.onerror = () => setState(s => ({ ...s, status: 'offline' }))
    } catch {
      setState(s => ({ ...s, status: 'offline' }))
    }
  }

  const handleMessage = (data: any) => {
    if (data.type === 'response') {
      setMessages(m => [...m, { role: 'vector', content: data.content, ts: new Date().toLocaleTimeString() }])
      setState(s => ({ ...s, status: 'online', lastAction: data.content.slice(0, 60) }))
    }
    if (data.type === 'state') setState(s => ({ ...s, ...data.payload }))
  }

  const updateUptime = () => {
    setState(s => {
      const [h, m, sec] = s.uptime.split(':').map(Number)
      const total = h * 3600 + m * 60 + sec + 1
      const hh = String(Math.floor(total / 3600)).padStart(2, '0')
      const mm = String(Math.floor((total % 3600) / 60)).padStart(2, '0')
      const ss = String(total % 60).padStart(2, '0')
      return { ...s, uptime: `${hh}:${mm}:${ss}` }
    })
  }

  const sendMessage = () => {
    if (!input.trim()) return
    const msg = { role: 'user', content: input, ts: new Date().toLocaleTimeString() }
    setMessages(m => [...m, msg])
    setState(s => ({ ...s, status: 'thinking', lastAction: input.slice(0, 60) }))
    wsRef.current?.send(JSON.stringify({ type: 'message', content: input }))
    setInput('')
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  return (
    <div className="hex-grid scanlines" style={{
      width: '100vw', height: '100vh',
      background: 'var(--jarvis-bg)',
      display: 'grid',
      gridTemplateRows: '48px 1fr 40px',
      gridTemplateColumns: '280px 1fr 260px',
      gap: '1px',
      overflow: 'hidden',
    }}>

      {/* ── Top bar ── */}
      <header style={{ gridColumn: '1/-1', gridRow: '1' }}
        className="jarvis-panel flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <VectorLogo size={28} />
          <span className="text-glow text-sm font-bold tracking-widest">V.E.C.T.O.R</span>
          <span className="text-xs" style={{ color: 'var(--jarvis-text-dim)' }}>
            VIRTUAL ENTITY FOR COGNITIVE TASKS &amp; OPERATIONAL REASONING
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--jarvis-text-dim)' }}>
          <span>UPTIME: <span style={{ color: 'var(--jarvis-cyan)' }}>{state.uptime}</span></span>
          <StatusIndicator status={state.status} />
        </div>
      </header>

      {/* ── Left panel — agents / districts ── */}
      <aside style={{ gridColumn: '1', gridRow: '2' }} className="jarvis-panel corner-tl overflow-hidden flex flex-col">
        <div className="flex border-b" style={{ borderColor: 'var(--jarvis-border)' }}>
          {(['agents', 'districts'] as const).map(p => (
            <button key={p} onClick={() => setActivePanel(p)}
              className="flex-1 py-2 text-xs tracking-widest uppercase transition-colors"
              style={{
                color: activePanel === p ? 'var(--jarvis-cyan)' : 'var(--jarvis-text-dim)',
                borderBottom: activePanel === p ? '1px solid var(--jarvis-cyan)' : 'none',
              }}>
              {p}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {activePanel === 'agents' && <AgentPanel activeAgents={state.activeAgents} />}
          {activePanel === 'districts' && <DistrictMap currentDistrict={state.district} />}
        </div>
      </aside>

      {/* ── Center — chat + mascot ── */}
      <main style={{ gridColumn: '2', gridRow: '2' }} className="jarvis-panel flex flex-col">
        {/* Mascot + core visual */}
        <div className="flex items-center justify-center" style={{ height: '180px', position: 'relative' }}>
          <VectorCore status={state.status} />
          <VectorMascot status={state.status} />
        </div>

        {/* Chat */}
        <div className="flex-1 overflow-hidden flex flex-col">
          <ChatPanel messages={messages} />
          <div className="p-3 border-t" style={{ borderColor: 'var(--jarvis-border)' }}>
            <div className="flex gap-2">
              <input
                className="jarvis-input flex-1 px-3 py-2 text-sm rounded"
                placeholder="Query VECTOR... (Enter to send)"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
              />
              <button onClick={sendMessage}
                className="jarvis-btn px-4 py-2 rounded">SEND</button>
            </div>
          </div>
        </div>
      </main>

      {/* ── Right panel — metrics + content pipeline ── */}
      <aside style={{ gridColumn: '3', gridRow: '2', display: 'flex', flexDirection: 'column', gap: 0 }}
             className="jarvis-panel corner-tl overflow-hidden">
        {/* System Metrics (top half) */}
        <div style={{ flex: '0 0 auto' }}>
          <div className="py-2 px-3 border-b" style={{ borderColor: 'var(--jarvis-border)' }}>
            <span className="label">System Metrics</span>
          </div>
          <div className="p-2">
            <SystemMetrics state={state} />
          </div>
        </div>
        {/* Content Pipeline (bottom half) */}
        <div style={{ flex: 1, minHeight: 0, borderTop: '1px solid rgba(0,212,255,0.1)', overflow: 'hidden' }}>
          <ContentPanel />
        </div>
      </aside>

      {/* ── Bottom status bar ── */}
      <footer style={{ gridColumn: '1/-1', gridRow: '3' }}>
        <StatusBar state={state} />
      </footer>

    </div>
  )
}

function VectorLogo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <polygon points="16,2 30,10 30,22 16,30 2,22 2,10"
        stroke="#00D4FF" strokeWidth="1.5" fill="rgba(0,212,255,0.1)" />
      <polygon points="16,7 26,13 26,19 16,25 6,19 6,13"
        stroke="#00D4FF" strokeWidth="0.5" fill="rgba(0,212,255,0.05)" />
      <text x="16" y="20" textAnchor="middle" fill="#00D4FF"
        fontSize="10" fontFamily="monospace" fontWeight="bold">V</text>
    </svg>
  )
}

function StatusIndicator({ status }: { status: AppStatus }) {
  const colors: Record<AppStatus, string> = {
    offline: '#FF3B30', connecting: '#FFB800', online: '#30FF6A',
    thinking: '#00D4FF', speaking: '#1A8FFF',
  }
  return (
    <div className="flex items-center gap-2">
      <div className="status-blink" style={{
        width: 8, height: 8, borderRadius: '50%',
        background: colors[status],
        boxShadow: `0 0 8px ${colors[status]}`,
      }} />
      <span style={{ color: colors[status] }}>{status.toUpperCase()}</span>
    </div>
  )
}
