import { useEffect, useRef } from 'react'
import { useVectorStore } from '../store/vectorStore'

const CX = 350
const CY = 350
const CYAN = '#00CFFF'
const RING_R = 110
const FACE_R = 106
const CIRC = Math.round(2 * Math.PI * RING_R) // 691

const GLOW_OPACITY: Record<string, number> = {
  idle: 0.28, listening: 0.65, processing: 0.42, speaking: 0.52,
}

const CENTER_TEXT: Record<string, string> = {
  idle: 'VECTOR', listening: 'LISTENING', processing: 'PROCESSING', speaking: 'RESPONDING',
}

const HOTSPOT_DUR: Record<string, string> = {
  idle: '8s', listening: '12s', processing: '6s', speaking: '4s',
}

const DIAMONDS = [45, 135, 225, 315].map((deg) => {
  const a = (deg * Math.PI) / 180
  return { cx: CX + 118 * Math.cos(a), cy: CY + 118 * Math.sin(a) }
})

const ARC77_CIRC = Math.round(2 * Math.PI * 77)
const ARC69_CIRC = Math.round(2 * Math.PI * 69)

export default function VectorCore() {
  const voiceState = useVectorStore((s) => s.voiceState)
  const orbInCorner = useVectorStore((s) => s.orbInCorner)
  const svgRef = useRef<SVGSVGElement>(null)

  const glowOpacity = GLOW_OPACITY[voiceState] ?? 0.28
  const centerText = CENTER_TEXT[voiceState] ?? 'VECTOR'
  const hotspotDur = HOTSPOT_DUR[voiceState] ?? '8s'

  useEffect(() => {
    if (voiceState !== 'processing') return
    const el = svgRef.current?.querySelector('#vc-center-text')
    if (!el) return
    let count = 0
    const id = setInterval(() => {
      count = (count + 1) % 4
      el.textContent = 'PROCESSING' + '.'.repeat(count)
    }, 400)
    return () => clearInterval(id)
  }, [voiceState])

  const scaledSize = Math.round(700 * 0.36) // 252
  const containerTransform = orbInCorner
    ? `translate(calc(100vw - ${scaledSize}px - 24px), calc(100vh - ${scaledSize}px - 24px)) scale(0.36)`
    : `translate(calc(50vw - 350px), calc(50vh - 350px)) scale(1)`

  return (
    <div style={{
      position: 'fixed',
      left: 0,
      top: 0,
      width: 700,
      height: 700,
      transform: containerTransform,
      transformOrigin: '0px 0px',
      transition: 'transform 0.4s cubic-bezier(0.4,0,0.2,1)',
      pointerEvents: 'none',
      zIndex: 10,
    }}>
      <style>{`
        @keyframes vc-hotspot  { from{stroke-dashoffset:0} to{stroke-dashoffset:-${CIRC}} }
        @keyframes vc-inner1   { from{transform:rotate(0deg)} to{transform:rotate(-360deg)} }
        @keyframes vc-inner2   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes vc-diamond-pulse { 0%,100%{opacity:0.55} 50%{opacity:1} }
      `}</style>
      <svg ref={svgRef} width={700} height={700} style={{ overflow: 'visible' }}>
        <defs>
          <filter id="vc-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
        </defs>

        {/* Dark orb face */}
        <circle cx={CX} cy={CY} r={FACE_R} fill="#05091a" />

        {/* Ambient glow ring (blurred) */}
        <circle cx={CX} cy={CY} r={RING_R} fill="none"
          stroke={CYAN} strokeWidth={10}
          opacity={glowOpacity}
          filter="url(#vc-glow)"
          style={{ transition: 'opacity 0.5s ease' }}
        />

        {/* Main ring (crisp) */}
        <circle cx={CX} cy={CY} r={RING_R} fill="none"
          stroke={CYAN} strokeWidth={3.5} opacity={0.9}
          style={{ filter: `drop-shadow(0 0 6px ${CYAN})` }}
        />

        {/* Hotspot arc (traveling clockwise) */}
        <circle cx={CX} cy={CY} r={RING_R} fill="none"
          stroke={CYAN} strokeWidth={3.5}
          strokeDasharray={`115 ${CIRC - 115}`}
          strokeLinecap="round"
          style={{
            animation: `vc-hotspot ${hotspotDur} linear infinite`,
            filter: `drop-shadow(0 0 10px ${CYAN})`,
            transformOrigin: `${CX}px ${CY}px`,
          }}
        />

        {/* Inner arc r=77 — 270° CCW 12s */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'vc-inner1 12s linear infinite' }}>
          <circle cx={CX} cy={CY} r={77} fill="none"
            stroke={CYAN} strokeWidth={1.2}
            strokeDasharray={`${Math.round(ARC77_CIRC * 0.75)} ${Math.round(ARC77_CIRC * 0.25)}`}
            opacity={0.22}
          />
        </g>

        {/* Inner arc r=69 — 90° CW 8s */}
        <g style={{ transformOrigin: `${CX}px ${CY}px`, animation: 'vc-inner2 8s linear infinite' }}>
          <circle cx={CX} cy={CY} r={69} fill="none"
            stroke={CYAN} strokeWidth={0.8}
            strokeDasharray={`${Math.round(ARC69_CIRC * 0.25)} ${Math.round(ARC69_CIRC * 0.75)}`}
            opacity={0.18}
          />
        </g>

        {/* Diamond markers at 45°/135°/225°/315° */}
        {DIAMONDS.map(({ cx, cy }, i) => (
          <rect key={i}
            x={cx - 3} y={cy - 3} width={6} height={6}
            fill={CYAN}
            transform={`rotate(45 ${cx} ${cy})`}
            opacity={0.7}
            style={{
              animation: 'vc-diamond-pulse 3s ease-in-out infinite',
              animationDelay: `${i * 0.5}s`,
            }}
          />
        ))}

        {/* Center text */}
        <text id="vc-center-text"
          x={CX} y={CY + 6}
          textAnchor="middle"
          fontFamily="'Orbitron', sans-serif"
          fontSize={voiceState === 'idle' ? 16 : 13}
          fontWeight="400"
          letterSpacing="0.25em"
          fill={CYAN}
          opacity={voiceState === 'idle' ? 0.9 : 0.75}
          style={{ filter: `drop-shadow(0 0 8px ${CYAN})` }}
        >
          {centerText}
        </text>

        <text x={CX} y={CY + 22}
          textAnchor="middle"
          fontFamily="'JetBrains Mono', monospace"
          fontSize={7}
          letterSpacing="0.3em"
          fill={CYAN}
          opacity={0.2}
        >
          AUTONOMOUS
        </text>
      </svg>
    </div>
  )
}
