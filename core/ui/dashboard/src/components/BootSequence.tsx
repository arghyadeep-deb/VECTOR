import { useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'

const CX = 350
const CY = 350
const CYAN = '#00CFFF'

type Phase = 'black' | 'core_dot' | 'core_glow' | 'ring1' | 'ring2' | 'rings34' | 'rings56' | 'text' | 'hud' | 'done'

const RING_DEFS = [
  { r: 70,  sw: 2,   dash: '',        dur: 30,  dir: 1  },
  { r: 110, sw: 1.5, dash: '8 4',     dur: 20,  dir: -1 },
  { r: 155, sw: 1,   dash: '',        dur: 45,  dir: 1  },
  { r: 205, sw: 1.5, dash: '20 8',    dur: 60,  dir: -1 },
  { r: 260, sw: 1,   dash: '2 6',     dur: 90,  dir: 1  },
  { r: 320, sw: 0.8, dash: '',        dur: 120, dir: -1 },
]

function Ticks({ r }: { r: number }) {
  return (
    <>
      {Array.from({ length: 48 }).map((_, i) => {
        const angle = (i / 48) * Math.PI * 2 - Math.PI / 2
        const len = i % 4 === 0 ? 10 : 5
        const x1 = CX + (r - len) * Math.cos(angle)
        const y1 = CY + (r - len) * Math.sin(angle)
        const x2 = CX + r * Math.cos(angle)
        const y2 = CY + r * Math.sin(angle)
        return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={CYAN} strokeWidth={i % 4 === 0 ? 1.5 : 0.8} opacity={0.5} />
      })}
    </>
  )
}

export default function BootSequence() {
  const bootDone = useVectorStore((s) => s.bootDone)
  const setBootDone = useVectorStore((s) => s.setBootDone)
  const [phase, setPhase] = useState<Phase>('black')
  const [visibleRings, setVisibleRings] = useState<number[]>([])

  useEffect(() => {
    if (bootDone) return
    const t = (delay: number, fn: () => void) => setTimeout(fn, delay)

    const ids = [
      t(300,  () => setPhase('core_dot')),
      t(800,  () => setPhase('core_glow')),
      t(1200, () => { setPhase('ring1'); setVisibleRings([0]) }),
      t(1600, () => { setPhase('ring2'); setVisibleRings([0, 1]) }),
      t(2000, () => { setPhase('rings34'); setVisibleRings([0, 1, 2, 3]) }),
      t(2500, () => { setPhase('rings56'); setVisibleRings([0, 1, 2, 3, 4, 5]) }),
      t(3000, () => setPhase('text')),
      t(3500, () => setPhase('hud')),
      t(4000, () => { setPhase('done'); setBootDone(true) }),
    ]
    return () => ids.forEach(clearTimeout)
  }, [bootDone, setBootDone])

  if (bootDone || phase === 'done') return null

  const coreSize = phase === 'black' ? 0 : phase === 'core_dot' ? 4 : 12
  const coreOpacity = phase === 'black' ? 0 : 1
  const textOpacity = phase === 'text' || phase === 'hud' ? 1 : 0

  return (
    <div style={{
      position: 'fixed', inset: 0, background: '#0a0e1a',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 9999,
    }}>
      <style>{`
        @keyframes bootRing { from { transform: scale(0); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        @keyframes cw30   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes ccw20  { from{transform:rotate(0deg)} to{transform:rotate(-360deg)} }
        @keyframes cw45   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes ccw60  { from{transform:rotate(0deg)} to{transform:rotate(-360deg)} }
        @keyframes cw90   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes ccw120 { from{transform:rotate(0deg)} to{transform:rotate(-360deg)} }
        @keyframes fadeIn { from{opacity:0} to{opacity:1} }
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');
      `}</style>

      <svg width={700} height={700} style={{ overflow: 'visible' }}>
        <defs>
          <radialGradient id="bootGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={CYAN} stopOpacity="1" />
            <stop offset="70%" stopColor={CYAN} stopOpacity="0.2" />
            <stop offset="100%" stopColor={CYAN} stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Core glow halo */}
        {coreSize > 4 && (
          <circle cx={CX} cy={CY} r={40} fill="url(#bootGlow)" opacity={0.5}
            style={{ transition: 'opacity 0.5s ease', filter: `blur(8px)` }} />
        )}

        {/* Core dot */}
        <circle cx={CX} cy={CY} r={coreSize} fill={CYAN} opacity={coreOpacity}
          style={{
            transition: 'r 0.5s ease, opacity 0.3s ease',
            filter: coreSize > 4 ? `drop-shadow(0 0 12px ${CYAN})` : 'none',
          }} />

        {/* Rings — appear one by one */}
        {RING_DEFS.map((ring, idx) => {
          if (!visibleRings.includes(idx)) return null
          const animName = ring.dir > 0
            ? ['cw30','cw30','cw45','cw45','cw90','cw30'][idx]
            : ['ccw20','ccw20','ccw60','ccw60','ccw120','ccw120'][idx]
          return (
            <g key={idx}
              style={{
                transformOrigin: `${CX}px ${CY}px`,
                animation: `${animName} ${ring.dur}s linear infinite`,
              }}>
              <g style={{
                transformOrigin: `${CX}px ${CY}px`,
                animation: `bootRing 0.4s ease-out forwards`,
              }}>
                <circle cx={CX} cy={CY} r={ring.r} fill="none" stroke={CYAN}
                  strokeWidth={ring.sw}
                  strokeDasharray={ring.dash || undefined}
                  opacity={0.55 - idx * 0.06} />
                {idx === 2 && <Ticks r={ring.r} />}
              </g>
            </g>
          )
        })}

        {/* Center text — fades in at 'text' phase */}
        <text x={CX} y={CY + 42} textAnchor="middle"
          fontFamily="'Orbitron', sans-serif" fontSize={16}
          fontWeight="400" letterSpacing="0.25em" fill={CYAN}
          opacity={textOpacity}
          style={{ transition: 'opacity 0.8s ease', animation: textOpacity ? 'fadeIn 0.8s ease forwards' : undefined }}>
          VECTOR
        </text>
        <text x={CX} y={CY + 58} textAnchor="middle"
          fontFamily="'JetBrains Mono', monospace" fontSize={7}
          letterSpacing="0.3em" fill={CYAN} opacity={textOpacity * 0.25}
          style={{ transition: 'opacity 0.8s ease' }}>
          AUTONOMOUS SYSTEM
        </text>

        {/* Boot status line */}
        <text x={CX} y={CY + 100} textAnchor="middle"
          fontFamily="'JetBrains Mono', monospace" fontSize={9}
          letterSpacing="0.15em" fill={CYAN} opacity={0.4}>
          {phase === 'black' ? '' :
           phase === 'core_dot' ? 'INITIALIZING...' :
           phase === 'core_glow' ? 'CORE ACTIVATED' :
           phase === 'ring1' ? 'LOADING INTERFACE...' :
           phase === 'ring2' ? 'EXPANDING SYSTEMS...' :
           phase === 'rings34' ? 'SYNCHRONIZING...' :
           phase === 'rings56' ? 'CALIBRATING...' :
           phase === 'text' ? 'VECTOR ONLINE' :
           'READY'}
        </text>
      </svg>
    </div>
  )
}
