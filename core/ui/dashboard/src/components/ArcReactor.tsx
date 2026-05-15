import { useRef, useEffect, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

const CROSSHAIR_COUNT = 4
const PARTICLE_COUNT = 8
const PARTICLE_RADIUS = 140

export default function ArcReactor() {
  const svgRef = useRef<SVGSVGElement>(null)
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)
  const events = useVectorStore((s) => s.events)
  const [pulse, setPulse] = useState(0)

  const mood = (() => {
    if (!events[0]) return 'idle'
    const t = events[0].event_type.toLowerCase()
    if (t.includes('error') || t.includes('warn')) return 'alert'
    if (t.includes('critical') || t.includes('die')) return 'alert'
    return goalsLen > 0 ? 'think' : 'idle'
  })()

  const isActive = mood === 'think'
  const isAlert = mood === 'alert'
  const orbColor = isAlert ? '#FF3D3D' : isActive ? '#81D4FA' : '#4FC3F7'
  const pulseDuration = isAlert ? 1.5 : isActive ? 2 : 3

  // Breathing pulse animation via JS
  useEffect(() => {
    let raf: number
    const start = Date.now()
    const animate = () => {
      const elapsed = (Date.now() - start) / 1000
      const t = (elapsed % pulseDuration) / pulseDuration
      // ease-in-out: smooth step
      const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
      setPulse(eased)
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [pulseDuration])

  // Pulse maps: 0 → min, 1 → max
  const glowRadius = 180 + pulse * 40 // 180–220px
  const crosshairExtend = pulse * 15 // 0–15px extension

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

      {/* Breathing glow — radius oscillates 180–220px */}
      <div style={{
        position: 'absolute', width: glowRadius * 2, height: glowRadius * 2,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${orbColor}15 0%, ${orbColor}08 50%, transparent 70%)`,
        filter: 'blur(20px)',
        transition: 'all 0.05s linear',
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
          {/* Hex grid pattern */}
          <pattern id="hexGrid" width="12" height="20.784" patternUnits="userSpaceOnUse">
            <path d="M6,0 L12,3.464 L12,10.392 L6,13.856 L0,10.392 L0,3.464 Z"
              fill="none" stroke={orbColor} strokeWidth="0.3" opacity="0.08"
              style={{ transition: 'stroke 0.8s ease' }} />
            <path d="M6,20.784 L12,17.32 L12,10.392"
              fill="none" stroke={orbColor} strokeWidth="0.3" opacity="0.08"
              style={{ transition: 'stroke 0.8s ease' }} />
          </pattern>
        </defs>

        {/* Outer glow circle */}
        <circle cx={cx} cy={cy} r={260} fill="url(#coreGlow)" opacity="0.3" />

        {/* Hex grid inside core */}
        <circle cx={cx} cy={cy} r={180} fill="url(#hexGrid)" opacity="0.8" />

        {/* Crosshair lines — extend/retract with pulse */}
        {Array.from({ length: CROSSHAIR_COUNT }, (_, i) => {
          const angle = (i * 360) / CROSSHAIR_COUNT
          const rad = (angle * Math.PI) / 180
          const baseLen = 160
          const len = baseLen + crosshairExtend
          return (
            <line
              key={`ch-${i}`}
              x1={cx + Math.cos(rad) * 30}
              y1={cy + Math.sin(rad) * 30}
              x2={cx + Math.cos(rad) * len}
              y2={cy + Math.sin(rad) * len}
              stroke={orbColor}
              strokeWidth="0.5"
              opacity="0.2"
              style={{ transition: 'stroke 0.8s ease' }}
            />
          )
        })}

        {/* Triangular/spoke structural frame */}
        {Array.from({ length: 6 }, (_, i) => {
          const angle = (i * 360) / 6
          const rad = (angle * Math.PI) / 180
          const r1 = 30, r2 = 200
          const x1 = cx + Math.cos(rad) * r1
          const y1 = cy + Math.sin(rad) * r1
          const x2 = cx + Math.cos(rad) * r2
          const y2 = cy + Math.sin(rad) * r2
          const x3 = cx + Math.cos(rad + 0.15) * r2 * 0.85
          const y3 = cy + Math.sin(rad + 0.15) * r2 * 0.85
          return (
            <polygon key={i}
              points={`${x1},${y1} ${x2},${y2} ${x3},${y3}`}
              fill="none" stroke={orbColor} strokeWidth="0.4" opacity="0.15"
              style={{ transition: 'stroke 0.8s ease' }}
            />
          )
        })}

        {/* Inner spoke ring */}
        {Array.from({ length: 6 }, (_, i) => {
          const angle = (i * 360) / 6
          const rad = (angle * Math.PI) / 180
          return (
            <line key={i}
              x1={cx + Math.cos(rad) * 30} y1={cy + Math.sin(rad) * 30}
              x2={cx + Math.cos(rad + Math.PI / 6) * 55} y2={cy + Math.sin(rad + Math.PI / 6) * 55}
              stroke={orbColor} strokeWidth="0.6" opacity="0.2"
              style={{ transition: 'stroke 0.8s ease' }}
            />
          )
        })}

        {/* Orbiting agent particles — 8 dots at radius 140px, staggered fade */}
        {Array.from({ length: PARTICLE_COUNT }, (_, i) => {
          const angle = (i * 360) / PARTICLE_COUNT
          const rad = (angle * Math.PI) / 180
          const x = cx + Math.cos(rad) * PARTICLE_RADIUS
          const y = cy + Math.sin(rad) * PARTICLE_RADIUS
          return (
            <circle key={`p-${i}`} cx={x} cy={y} r="2" fill={orbColor} opacity="0.6"
              style={{ transition: 'fill 0.8s ease' }}>
              <animate attributeName="opacity"
                values="0.05;0.5;0.05"
                dur={`${2 + i * 0.5}s`}
                begin={`-${i * 0.7}s`}
                repeatCount="indefinite" />
            </circle>
          )
        })}

        {/* Radiating beam lines */}
        {isActive && Array.from({ length: 12 }, (_, i) => {
          const angle = (i * 360) / 12
          const rad = (angle * Math.PI) / 180
          return (
            <line key={i}
              x1={cx + Math.cos(rad) * 35} y1={cy + Math.sin(rad) * 35}
              x2={cx + Math.cos(rad) * (220 + Math.sin(Date.now() * 0.002 + i) * 40)}
              y2={cy + Math.sin(rad) * (220 + Math.sin(Date.now() * 0.002 + i) * 40)}
              stroke={orbColor} strokeWidth="0.3" opacity="0.15"
              style={{ transition: 'stroke 0.8s ease' }}>
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
