import { useRef, useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

const RINGS = [
  { r: 220, sw: 0.6, dash: '6 12', speed: 0.15, tilt: 0, opacity: 0.12 },
  { r: 190, sw: 0.4, dash: '3 8', speed: -0.25, tilt: 5, opacity: 0.1 },
  { r: 160, sw: 0.8, dash: '10 20', speed: 0.2, tilt: -3, opacity: 0.15 },
  { r: 130, sw: 0.3, dash: '2 6', speed: -0.3, tilt: 8, opacity: 0.08 },
  { r: 100, sw: 0.6, dash: '4 12', speed: 0.35, tilt: -5, opacity: 0.12 },
  { r: 70, sw: 0.4, dash: '2 5', speed: -0.4, tilt: 0, opacity: 0.1 },
  { r: 45, sw: 0.5, dash: '3 7', speed: 0.5, tilt: 0, opacity: 0.15 },
]

const BEAMS = 12
const TRIANGLE_POINTS = 6

export default function ArcReactor() {
  const svgRef = useRef<SVGSVGElement>(null)
  const anglesRef = useRef(RINGS.map(() => 0))
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)
  const events = useVectorStore((s) => s.events)

  const mood = (() => {
    if (!events[0]) return 'idle'
    const t = events[0].event_type.toLowerCase()
    if (t.includes('error') || t.includes('warn')) return 'alert'
    if (t.includes('critical') || t.includes('die')) return 'alert'
    return goalsLen > 0 ? 'think' : 'idle'
  })()

  const isActive = mood === 'think'
  const isAlert = mood === 'alert'
  const orbColor = isAlert ? '#FF3D3D' : isActive ? '#00FFD4' : '#00d4ff'
  const speedMult = isActive ? 2.5 : isAlert ? 3 : 1

  useEffect(() => {
    if (!svgRef.current) return
    const rings = svgRef.current.querySelectorAll('.arc-ring')
    let raf = 0

    const animate = () => {
      anglesRef.current = anglesRef.current.map((a, i) => {
        const next = a + RINGS[i].speed * speedMult
        if (rings[i]) {
          (rings[i] as SVGCircleElement).setAttribute('stroke-dashoffset', String((next * 10) % (RINGS[i].r * 6)))
        }
        return next
      })
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [speedMult])

  const cx = 400, cy = 200

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      zIndex: Z.ARC_REACTOR, pointerEvents: 'none', overflow: 'visible',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      {/* Outer glow */}
      <div style={{
        width: 560, height: 560, borderRadius: '50%',
        background: `radial-gradient(circle, ${orbColor}06 0%, ${orbColor}03 40%, transparent 70%)`,
        filter: 'blur(60px)',
        transition: 'all 0.8s ease',
      }} />

      {/* Mid aura */}
      <div style={{
        position: 'absolute', width: 380, height: 380, borderRadius: '50%',
        background: `radial-gradient(circle, ${orbColor}12 0%, ${orbColor}06 50%, transparent 70%)`,
        filter: 'blur(25px)',
        animation: `breathe ${isAlert ? 1.5 : isActive ? 2 : 3}s ease-in-out infinite`,
        transition: 'all 0.8s ease',
      }} />

      {/* SVG arc reactor layer */}
      <svg
        ref={svgRef}
        style={{
          position: 'absolute', width: 800, height: 400,
          overflow: 'visible', filter: `drop-shadow(0 0 15px ${orbColor}44)`,
          transition: 'filter 0.8s ease',
        }}
        viewBox="0 0 800 400"
      >
        <defs>
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="20%" stopColor="#ffffff" stopOpacity="0.8" />
            <stop offset="40%" stopColor={orbColor} stopOpacity="0.6" />
            <stop offset="70%" stopColor={orbColor} stopOpacity="0.15" />
            <stop offset="100%" stopColor={orbColor} stopOpacity="0" />
          </radialGradient>
          <filter id="coreFilter">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Outer glow circle */}
        <circle cx={cx} cy={cy} r={260} fill="url(#coreGlow)" opacity="0.3" />

        {/* Concentric rotating rings */}
        {RINGS.map((ring, i) => (
          <circle
            key={i}
            className="arc-ring"
            cx={cx} cy={cy} r={ring.r}
            fill="none"
            stroke={orbColor}
            strokeWidth={ring.sw}
            strokeDasharray={ring.dash}
            opacity={ring.opacity}
            style={{
              transform: `rotateX(${ring.tilt}deg)`,
              transformOrigin: `${cx}px ${cy}px`,
              transition: 'stroke 0.8s ease',
            }}
          />
        ))}

        {/* Triangular/spoke structural frame */}
        {Array.from({ length: TRIANGLE_POINTS }, (_, i) => {
          const angle = (i * 360) / TRIANGLE_POINTS
          const rad = (angle * Math.PI) / 180
          const r1 = 30, r2 = 200
          const x1 = cx + Math.cos(rad) * r1
          const y1 = cy + Math.sin(rad) * r1
          const x2 = cx + Math.cos(rad) * r2
          const y2 = cy + Math.sin(rad) * r2
          const x3 = cx + Math.cos(rad + 0.15) * r2 * 0.85
          const y3 = cy + Math.sin(rad + 0.15) * r2 * 0.85
          return (
            <polygon
              key={i}
              points={`${x1},${y1} ${x2},${y2} ${x3},${y3}`}
              fill="none"
              stroke={orbColor}
              strokeWidth="0.4"
              opacity="0.15"
              style={{ transition: 'stroke 0.8s ease' }}
            />
          )
        })}

        {/* Inner spoke ring (connecting triangles) */}
        {Array.from({ length: TRIANGLE_POINTS }, (_, i) => {
          const angle = (i * 360) / TRIANGLE_POINTS
          const rad = (angle * Math.PI) / 180
          const x1 = cx + Math.cos(rad) * 30
          const y1 = cy + Math.sin(rad) * 30
          const x2 = cx + Math.cos(rad + Math.PI / TRIANGLE_POINTS) * 55
          const y2 = cy + Math.sin(rad + Math.PI / TRIANGLE_POINTS) * 55
          return (
            <line
              key={i}
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke={orbColor}
              strokeWidth="0.6"
              opacity="0.2"
              style={{ transition: 'stroke 0.8s ease' }}
            />
          )
        })}

        {/* Radiating beam lines */}
        {isActive && Array.from({ length: BEAMS }, (_, i) => {
          const angle = (i * 360) / BEAMS
          const rad = (angle * Math.PI) / 180
          const len = 220 + Math.sin(Date.now() * 0.002 + i) * 40
          return (
            <line
              key={i}
              x1={cx + Math.cos(rad) * 35}
              y1={cy + Math.sin(rad) * 35}
              x2={cx + Math.cos(rad) * len}
              y2={cy + Math.sin(rad) * len}
              stroke={orbColor}
              strokeWidth="0.3"
              opacity="0.15"
              style={{ transition: 'stroke 0.8s ease' }}
            >
              <animate attributeName="opacity" values="0.05;0.2;0.05" dur={`${1 + i * 0.2}s`} repeatCount="indefinite" />
            </line>
          )
        })}

        {/* Center bright core */}
        <circle cx={cx} cy={cy} r={20} fill="#ffffff" filter="url(#coreFilter)" opacity="0.95" />
        <circle cx={cx} cy={cy} r={10} fill="#ffffff" opacity="1" />

        {/* Inner glow bead */}
        <circle cx={cx} cy={cy} r={35} fill="none" stroke={orbColor} strokeWidth="1.5" opacity="0.3"
          style={{ transition: 'stroke 0.8s ease' }}>
          {isActive && <animate attributeName="r" values="35;40;35" dur="2s" repeatCount="indefinite" />}
          {isActive && <animate attributeName="opacity" values="0.3;0.1;0.3" dur="2s" repeatCount="indefinite" />}
        </circle>
      </svg>

      {/* Core orb */}
      <div style={{
        position: 'absolute', width: 80, height: 80, borderRadius: '50%',
        background: `radial-gradient(circle, rgba(255,255,255,0.95) 0%, ${orbColor}88 40%, transparent 70%)`,
        boxShadow: `0 0 60px ${orbColor}66, 0 0 150px ${orbColor}33, 0 0 300px ${orbColor}11`,
        animation: `breathe ${isAlert ? 1.5 : isActive ? 2 : 3}s ease-in-out infinite`,
        transition: 'all 0.8s ease',
      }} />

      {/* Inner bright core point */}
      <div style={{
        position: 'absolute', width: 20, height: 20, borderRadius: '50%',
        background: 'rgba(255,255,255,1)',
        boxShadow: `0 0 20px ${orbColor}, 0 0 50px ${orbColor}88`,
        transition: 'all 0.8s ease',
      }} />
    </div>
  )
}
