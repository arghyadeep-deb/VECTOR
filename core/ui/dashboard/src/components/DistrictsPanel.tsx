import { useMemo } from 'react'
import { useVectorStore } from '../store/vectorStore'

const DISTRICT_ORDER = [
  'coding', 'finance', 'governance', 'health', 'memory_curator',
  'projects', 'reflection', 'research', 'security', 'time_calendar',
]

function hpColor(hp: number): string {
  if (hp >= 700) return '#BF5FFF'
  if (hp >= 400) return '#00CFFF'
  if (hp >= 100) return '#FFB300'
  return '#FF3D3D'
}

export default function DistrictsPanel() {
  const openPanel = useVectorStore((s) => s.openPanel)
  const agents = useVectorStore((s) => s.agents)
  const status = useVectorStore((s) => s.status)

  const districtData = useMemo(() => {
    const s = new Set<string>()
    agents.forEach((a) => { if (a.district) s.add(a.district.toLowerCase()) })
    const names = DISTRICT_ORDER.filter((d) => s.has(d))
    const extras = Array.from(s).filter((d) => !DISTRICT_ORDER.includes(d)).sort()
    const ordered = [...names, ...extras]

    const map = new Map<string, { aliveCount: number; totalHP: number; agentsCount: number }>()
    for (const name of ordered) {
      const da = agents.filter((a) => a.district?.toLowerCase() === name)
      const alive = da.filter((a) => a.is_alive)
      map.set(name, {
        aliveCount: alive.length,
        totalHP: alive.reduce((s, a) => s + a.health_points, 0),
        agentsCount: da.length,
      })
    }
    return { ordered, map }
  }, [agents])

  const totalAlive = agents.filter((a) => a.is_alive).length

  return (
    <div style={{
      position: 'fixed', top: 45, right: 0, width: 196,
      height: 'calc(100vh - 110px)', overflowY: 'auto', overflowX: 'hidden',
      zIndex: 30, background: 'rgba(5,13,26,0.9)',
      borderLeft: '1px solid rgba(0,212,255,0.08)',
      boxShadow: '-4px 0 30px rgba(0,212,255,0.04), inset 0 0 30px rgba(0,212,255,0.02)',
      backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
      scrollbarWidth: 'thin' as any, scrollbarColor: 'rgba(0,212,255,0.06) transparent',
      transition: 'border-color 0.8s ease',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px', borderBottom: '1px solid rgba(0,207,255,0.08)',
        fontFamily: "'Orbitron', sans-serif", fontSize: 11, color: '#00CFFF',
        letterSpacing: '0.18em',
      }}>
        <span>DISTRICTS</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#004466' }}>{districtData.ordered.length}</span>
      </div>

      <style>{`.dentry{cursor:pointer;transition:all .15s}.dentry:hover{background:rgba(0,207,255,0.04)}`}</style>

      {districtData.ordered.map((name) => {
        const data = districtData.map.get(name)
        const isLive = (data?.aliveCount ?? 0) > 0
        const avgHP = data && data.aliveCount > 0 ? Math.round(data.totalHP / data.aliveCount) : 0

        return (
          <div
            key={name}
            className="dentry"
            onClick={() => openPanel({ id: `district-${name}`, type: 'district', districtName: name })}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '7px 14px', borderBottom: '1px solid rgba(0,207,255,0.03)',
            }}
          >
            <span style={{
              width: 4, height: 4, borderRadius: '50%', flexShrink: 0,
              background: isLive ? '#00CFFF' : '#2a2a2a',
              boxShadow: isLive ? '0 0 8px #00CFFF' : 'none',
              animation: isLive ? 'v-pulse 3s ease-in-out infinite' : 'none',
            }} />
            <span style={{
              fontFamily: "'Orbitron', sans-serif", fontSize: 12, fontWeight: 500,
              color: isLive ? '#7ecfed' : '#3a4a5a', letterSpacing: '0.1em',
              flex: 1,
            }}>
              {name}
            </span>
            {isLive && (
              <span style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                color: hpColor(avgHP), minWidth: 20, textAlign: 'right',
              }}>
                {avgHP}
              </span>
            )}
          </div>
        )
      })}

      <div style={{
        padding: '8px 14px', borderTop: '1px solid rgba(0,207,255,0.06)',
        fontFamily: "'Orbitron', sans-serif", fontSize: 11, color: '#1a6688',
        letterSpacing: '0.1em', display: 'flex', justifyContent: 'space-between',
      }}>
        <span>AGENTS ONLINE</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#00FF88' }}>{totalAlive}</span>
      </div>
    </div>
  )
}
