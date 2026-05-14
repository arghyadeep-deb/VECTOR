import { useVectorStore } from '../store/vectorStore'
import { useScramble } from '../hooks/useScramble'

function Capability({ label, active }: { label: string; active: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px 0' }}>
      <span style={{
        width: 4, height: 4, borderRadius: '50%', flexShrink: 0,
        background: active ? '#00FF88' : '#2a2a2a',
        boxShadow: active ? '0 0 6px #00FF88' : 'none',
        animation: active ? 'v-pulse 3s ease-in-out infinite' : 'none',
      }} />
      <span style={{
        fontFamily: "'Orbitron', sans-serif", fontSize: 10,
        color: active ? '#7ecfed' : '#3a4a5a', letterSpacing: '0.1em',
      }}>
        {label}
      </span>
    </div>
  )
}

function hpColor(hp: number): string {
  if (hp >= 700) return '#BF5FFF'
  if (hp >= 400) return '#00CFFF'
  if (hp >= 100) return '#FFB300'
  return '#FF3D3D'
}

export default function TelemetryPanel() {
  const m = useVectorStore((s) => s.systemMetrics)
  const agents = useVectorStore((s) => s.agents)
  const status = useVectorStore((s) => s.status)
  const errors = useVectorStore((s) => s.connectionErrors)

  const cpu = m?.cpu_percent ?? 0
  const memPct = m?.memory_percent ?? 0
  const memUsed = m?.memory_used_gb ?? 0
  const memTotal = m?.memory_total_gb ?? 1
  const diskPct = m?.disk_percent ?? 0

  const hp = agents.reduce((sum, a) => sum + (a.health_points || 0), 0)
  const alive = agents.filter((a) => a.is_alive).length
  const total = agents.length
  const atRisk = agents.filter((a) => a.is_alive && (a.health_points ?? 0) < 300).length

  const hasError = errors['/status']?.failed || errors['/agents']?.failed
  const offline = !status && hasError
  const sysColor = hpColor(hp)
  const hpScramble = useScramble(hp)

  const memCount = typeof status?.memory?.episodic_count === 'number' ? (status.memory.episodic_count as number) : 0
  const memEvents = Math.min(999, Math.round(memCount))
  const gpuMem = m?.gpu_mem_percent ?? 0

  const hasCoder = agents.some((a) => a.district === 'coding' && a.is_alive)
  const hasFocus = agents.some((a) => a.status === 'active' || a.status === 'thinking')
  const reasoningDepth = Math.min(10, Math.max(1, Math.round(alive / 2)))
  const hasMultilingual = total >= 6
  const models = status?.models ? Object.values(status.models) : []
  const modelList = [...new Set(models)].join(', ')

  const memBarColor = memPct > 70 ? '#FFB300' : memPct > 40 ? '#00d4ff' : '#00FF88'

  return (
    <div style={{
      width: '100%',
      zIndex: 40, background: 'rgba(5,13,26,0.88)',
      backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)',
      border: '1px solid rgba(0,212,255,0.08)',
      boxShadow: '0 0 30px rgba(0,212,255,0.04), inset 0 0 30px rgba(0,212,255,0.02)',
      paddingBottom: 4,
    }}>
      {/* TELEMETRY section header */}
      <div style={{
        fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688',
        letterSpacing: '0.15em', padding: '6px 10px 4px',
        borderBottom: '1px solid rgba(0,207,255,0.06)',
      }}>
        TELEMETRY
      </div>

      {/* SYS row */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)',
      }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#3388aa', letterSpacing: '0.1em' }}>SYS</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>
          {Math.round(cpu)}% CPU · {Math.round(memPct)}% MEM · {Math.round(diskPct)}% DSK
        </span>
      </div>

      {/* MEM LOAD bar */}
      <div style={{ padding: '4px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688', letterSpacing: '0.08em' }}>MEM LOAD</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: memBarColor }}>{Math.round(memPct)}%</span>
        </div>
        <div style={{ height: 3, background: 'rgba(0,207,255,0.04)', border: '1px solid rgba(0,207,255,0.06)', borderRadius: 1, overflow: 'hidden' }}>
          <div style={{
            width: `${Math.min(100, memPct)}%`, height: '100%',
            background: memBarColor, boxShadow: `0 0 6px ${memBarColor}66`,
            transition: 'width 0.8s ease',
          }} />
        </div>
      </div>

      {/* Memory + Agents row */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)',
      }}>
        <div>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688', letterSpacing: '0.08em' }}>MEMORY</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>{memUsed.toFixed(1)}/{memTotal.toFixed(0)}G</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688', letterSpacing: '0.08em' }}>AGENTS</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#00d4ff' }}>C {total}</div>
        </div>
      </div>

      {/* AGENTS ALIVE + MEMORY events row */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '4px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)',
      }}>
        <div>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688', letterSpacing: '0.08em' }}>AGENTS ALIVE</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: alive === total ? '#00FF88' : '#FFB300' }}>{alive}/{total}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688', letterSpacing: '0.08em' }}>MEMORY</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff' }}>{memEvents} ev</div>
        </div>
      </div>

      {/* SYSTEM HP */}
      <div style={{
        padding: '6px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688', letterSpacing: '0.1em' }}>SYSTEM HP</span>
        <span style={{
          fontFamily: "'Orbitron', sans-serif", fontSize: 16, fontWeight: 600,
          color: sysColor, lineHeight: 1,
          textShadow: `0 0 20px ${sysColor}55`,
        }}>
          {offline ? '—' : hpScramble}
        </span>
      </div>

      {/* Capabilities */}
      <div style={{
        padding: '4px 10px', borderBottom: '1px solid rgba(0,207,255,0.04)',
      }}>
        <div style={{
          fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688',
          letterSpacing: '0.1em', marginBottom: 2,
        }}>
          CAPABILITIES
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 8px' }}>
          <Capability label="CODER" active={hasCoder} />
          <Capability label="FOCUS" active={hasFocus} />
          <Capability label="REASONING" active={reasoningDepth >= 3} />
          <Capability label="MULTILINGUAL" active={hasMultilingual} />
        </div>
      </div>

      {/* MODELS */}
      <div style={{ padding: '4px 10px' }}>
        <div style={{
          fontFamily: "'Orbitron', sans-serif", fontSize: 10, color: '#1a6688',
          letterSpacing: '0.1em', marginBottom: 1,
        }}>
          MODELS
        </div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#7ecfed',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {modelList || '—'}
        </div>
      </div>
    </div>
  )
}
