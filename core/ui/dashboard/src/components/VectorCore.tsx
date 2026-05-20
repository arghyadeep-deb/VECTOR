import { useEffect, useRef } from 'react'
import { useVectorStore } from '../store/vectorStore'

const CX = 350
const CY = 350
const CYAN = '#00CFFF'

// Tick marks for ring 3
function Ticks({ r, count, opacity }: { r: number; count: number; opacity: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => {
        const angle = (i / count) * Math.PI * 2 - Math.PI / 2
        const len = i % 4 === 0 ? 10 : 5
        const x1 = CX + (r - len) * Math.cos(angle)
        const y1 = CY + (r - len) * Math.sin(angle)
        const x2 = CX + r * Math.cos(angle)
        const y2 = CY + r * Math.sin(angle)
        return (
          <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={CYAN} strokeWidth={i % 4 === 0 ? 1.5 : 0.8} opacity={opacity} />
        )
      })}
    </>
  )
}

// Segmented arc ring for ring 4
function SegmentedRing({ r, segments, gapDeg, opacity }: { r: number; segments: number; gapDeg: number; opacity: number }) {
  const gap = (gapDeg * Math.PI) / 180
  const segAngle = (Math.PI * 2 - segments * gap) / segments
  const arcs: string[] = []
  for (let i = 0; i < segments; i++) {
    const startAngle = i * (segAngle + gap) - Math.PI / 2
    const endAngle = startAngle + segAngle
    const x1 = CX + r * Math.cos(startAngle)
    const y1 = CY + r * Math.sin(startAngle)
    const x2 = CX + r * Math.cos(endAngle)
    const y2 = CY + r * Math.sin(endAngle)
    arcs.push(`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`)
  }
  return (
    <>
      {arcs.map((d, i) => (
        <path key={i} d={d} fill="none" stroke={CYAN} strokeWidth={1.5} opacity={opacity} />
      ))}
    </>
  )
}

// Cardinal marker squares on ring 6
function CardinalMarkers({ r, opacity }: { r: number; opacity: number }) {
  return (
    <>
      {[0, 90, 180, 270].map((deg, i) => {
        const angle = (deg * Math.PI) / 180 - Math.PI / 2
        const mx = CX + r * Math.cos(angle)
        const my = CY + r * Math.sin(angle)
        return (
          <rect key={i} x={mx - 4} y={my - 4} width={8} height={8}
            fill={CYAN} opacity={opacity} transform={`rotate(45 ${mx} ${my})`} />
        )
      })}
    </>
  )
}

export default function VectorCore() {
  const voiceState = useVectorStore((s) => s.voiceState)
  const svgRef = useRef<SVGSVGElement>(null)

  // Glow intensity by voice state
  const glowMap: Record<string, number> = { idle: 0.45, listening: 1.0, processing: 0.7, speaking: 0.85 }
  const glow = glowMap[voiceState] ?? 0.45

  // Center text by voice state
  const textMap: Record<string, string> = { idle: 'VECTOR', listening: 'LISTENING', processing: 'PROCESSING', speaking: 'RESPONDING' }
  const centerText = textMap[voiceState] ?? 'VECTOR'

  // Animate dots for processing
  const dotRef = useRef(0)
  const dotState = useRef('')
  useEffect(() => {
    if (voiceState !== 'processing') { dotState.current = ''; return }
    const id = setInterval(() => {
      dotRef.current = (dotRef.current + 1) % 4
      const svg = svgRef.current
      if (svg) {
        const el = svg.querySelector('#center-text')
        if (el) el.textContent = 'PROCESSING' + '.'.repeat(dotRef.current)
      }
    }, 400)
    return () => clearInterval(id)
  }, [voiceState])

  const coreOpacity = voiceState === 'listening' ? 1 : 0.85
  const ringBaseOpacity = glow

  return (
    <div style={{
      position: 'fixed',
      top: '50%', left: '50%',
      transform: 'translate(-50%, -50%)',
      width: 700, height: 700,
      pointerEvents: 'none',
      zIndex: 10,
    }}>
      <svg ref={svgRef} width={700} height={700} style={{ overflow: 'visible', filter: `drop-shadow(0 0 ${Math.round(glow * 16)}px ${CYAN}44)` }}>
        <defs>
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={CYAN} stopOpacity="1" />
            <stop offset="60%" stopColor={CYAN} stopOpacity="0.3" />
            <stop offset="100%" stopColor={CYAN} stopOpacity="0" />
          </radialGradient>
          <filter id="blur-core">
            <feGaussianBlur stdDeviation="6" />
          </filter>
          <style>{`
            @keyframes cw30  { from { transform: rotate(0deg);    } to { transform: rotate(360deg);  } }
            @keyframes ccw20 { from { transform: rotate(0deg);    } to { transform: rotate(-360deg); } }
            @keyframes cw45  { from { transform: rotate(0deg);    } to { transform: rotate(360deg);  } }
            @keyframes ccw60 { from { transform: rotate(0deg);    } to { transform: rotate(-360deg); } }
            @keyframes cw90  { from { transform: rotate(0deg);    } to { transform: rotate(360deg);  } }
            @keyframes ccw120{ from { transform: rotate(0deg);    } to { transform: rotate(-360deg); } }
            @keyframes pulse { 0%,100%{opacity:0.9} 50%{opacity:0.4} }
            @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.6} }
            @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');
          `}</style>
        </defs>

        {/* Outer ambient glow */}
        <circle cx={CX} cy={CY} r={340} fill="none"
          stroke={CYAN} strokeWidth={1} opacity={0.03} />

        {/* Ring 6 — outermost, very slow CCW (120s) */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'ccw120 120s linear infinite' }}>
          <circle cx={CX} cy={CY} r={320} fill="none" stroke={CYAN}
            strokeWidth={0.8} opacity={ringBaseOpacity * 0.18} />
          <CardinalMarkers r={320} opacity={ringBaseOpacity * 0.35} />
        </g>

        {/* Ring 5 — square notches, slow CW (90s) */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'cw90 90s linear infinite' }}>
          <circle cx={CX} cy={CY} r={260} fill="none" stroke={CYAN}
            strokeWidth={1} opacity={ringBaseOpacity * 0.22} strokeDasharray="2 6" />
        </g>

        {/* Ring 4 — segmented arcs, CCW (60s) */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'ccw60 60s linear infinite' }}>
          <SegmentedRing r={205} segments={12} gapDeg={4} opacity={ringBaseOpacity * 0.35} />
        </g>

        {/* Ring 3 — tick marks, CW (45s) */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'cw45 45s linear infinite' }}>
          <circle cx={CX} cy={CY} r={155} fill="none" stroke={CYAN}
            strokeWidth={1} opacity={ringBaseOpacity * 0.45} />
          <Ticks r={155} count={48} opacity={ringBaseOpacity * 0.5} />
        </g>

        {/* Ring 2 — dashed, CCW (20s) */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'ccw20 20s linear infinite' }}>
          <circle cx={CX} cy={CY} r={110} fill="none" stroke={CYAN}
            strokeWidth={1.5} strokeDasharray="8 4" opacity={ringBaseOpacity * 0.6} />
        </g>

        {/* Ring 1 — solid, slow CW (30s) */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'cw30 30s linear infinite' }}>
          <circle cx={CX} cy={CY} r={70} fill="none" stroke={CYAN}
            strokeWidth={2} opacity={ringBaseOpacity * 0.75} />
          {/* 4 notches on ring 1 */}
          {[0, 90, 180, 270].map((deg, i) => {
            const a = (deg * Math.PI) / 180 - Math.PI / 2
            return (
              <line key={i}
                x1={CX + 64 * Math.cos(a)} y1={CY + 64 * Math.sin(a)}
                x2={CX + 76 * Math.cos(a)} y2={CY + 76 * Math.sin(a)}
                stroke={CYAN} strokeWidth={3} opacity={ringBaseOpacity} />
            )
          })}
        </g>

        {/* Core glow halo */}
        <circle cx={CX} cy={CY} r={32} fill="url(#coreGlow)" opacity={coreOpacity * 0.6}
          style={{ animation: voiceState === 'listening' ? 'pulse 1s ease-in-out infinite' : undefined }} />

        {/* Core dot */}
        <circle cx={CX} cy={CY} r={voiceState === 'listening' ? 14 : 10}
          fill={CYAN} opacity={coreOpacity}
          style={{
            filter: `drop-shadow(0 0 12px ${CYAN})`,
            transition: 'r 0.3s ease',
            animation: voiceState === 'listening' ? 'pulse 0.8s ease-in-out infinite' : undefined,
          }} />

        {/* Center text */}
        <text id="center-text" x={CX} y={CY + 42} textAnchor="middle"
          fontFamily="'Orbitron', sans-serif" fontSize={voiceState === 'idle' ? 16 : 13}
          fontWeight="400" letterSpacing="0.25em" fill={CYAN}
          opacity={voiceState === 'idle' ? 0.9 : 0.75}
          style={{
            animation: voiceState === 'listening' ? 'blink 1.2s ease-in-out infinite'
              : voiceState === 'speaking' ? 'blink 0.6s ease-in-out infinite' : undefined,
          }}>
          {centerText}
        </text>

        {/* Sub-label */}
        <text x={CX} y={CY + 58} textAnchor="middle"
          fontFamily="'JetBrains Mono', monospace" fontSize={7}
          letterSpacing="0.3em" fill={CYAN} opacity={0.25}>
          AUTONOMOUS SYSTEM
        </text>
      </svg>
    </div>
  )
}
