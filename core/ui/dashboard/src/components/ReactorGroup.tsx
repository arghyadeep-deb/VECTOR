import { useRef, useEffect, useState, useCallback } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

const CROSSHAIR_COUNT = 4
const PARTICLE_COUNT = 8
const PARTICLE_RADIUS = 140

const RINGS = [
  { rx: 320, ry: 80, tilt: 10, speed: 0.2, opacity: 0.15 },
  { rx: 260, ry: 100, tilt: -15, speed: -0.3, opacity: 0.12 },
  { rx: 200, ry: 60, tilt: 25, speed: 0.25, opacity: 0.18 },
  { rx: 150, ry: 50, tilt: -5, speed: -0.35, opacity: 0.15 },
]

const PARTICLE_RINGS = [
  { rx: 345, ry: 115, count: 3, dur: 18, tilt: 8 },
  { rx: 275, ry: 85,  count: 4, dur: 14, tilt: -12 },
  { rx: 195, ry: 58,  count: 5, dur: 10, tilt: 20 },
]

const PATHWAYS = [
  { angle: 0, length: 180, branches: 3 },
  { angle: 45, length: 140, branches: 2 },
  { angle: 90, length: 200, branches: 4 },
  { angle: 135, length: 150, branches: 2 },
  { angle: 180, length: 170, branches: 3 },
  { angle: 225, length: 130, branches: 2 },
  { angle: 270, length: 190, branches: 3 },
  { angle: 315, length: 160, branches: 2 },
]

const TRACES = [
  { side: 'left', yOff: -60, label: 'TELEMETRY' },
  { side: 'left', yOff: 0, label: 'COMMAND' },
  { side: 'left', yOff: 60, label: 'EVENTS' },
  { side: 'right', yOff: -80, label: 'DISTRICTS' },
  { side: 'right', yOff: 0, label: 'COUNCIL' },
  { side: 'right', yOff: 80, label: 'ANALYTICS' },
]

function ellipsePath(cx: number, cy: number, rx: number, ry: number): string {
  return `M ${cx - rx},${cy} A ${rx},${ry} 0 1,1 ${cx + rx},${cy} A ${rx},${ry} 0 1,1 ${cx - rx},${cy}`
}

export default function ReactorGroup() {
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const offsetRef = useRef({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const isDraggingRef = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const offsetStart = useRef({ x: 0, y: 0 })
  const svgRef = useRef<SVGSVGElement>(null)
  const anglesRef = useRef(RINGS.map(() => 0))
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)
  const events = useVectorStore((s) => s.events)
  const [pulse, setPulse] = useState(0)

  const mood = (() => {
    if (!events[0]) return 'idle'
    const t = events[0].event_type.toLowerCase()
    if (t.includes('error') || t.includes('warn') || t.includes('critical') || t.includes('die')) return 'alert'
    return goalsLen > 0 ? 'think' : 'idle'
  })()

  const isActive = mood === 'think'
  const isAlert = mood === 'alert'
  const orbColor = isAlert ? '#FF3D3D' : isActive ? '#81D4FA' : '#4FC3F7'
  const pulseDuration = isAlert ? 1.5 : isActive ? 2 : 3

  useEffect(() => {
    let raf: number
    const start = Date.now()
    const animate = () => {
      const elapsed = (Date.now() - start) / 1000
      const t = (elapsed % pulseDuration) / pulseDuration
      setPulse(t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2)
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [pulseDuration])

  const glowRadius = 180 + pulse * 40
  const crosshairExtend = pulse * 15

  useEffect(() => {
    if (!svgRef.current) return
    const paths = svgRef.current.querySelectorAll('ellipse.holo-ring')
    let raf = 0
    const speedMult = goalsLen > 0 ? 2.5 : 1
    const animate = () => {
      anglesRef.current = anglesRef.current.map((a, i) => {
        const next = a + RINGS[i].speed * speedMult
        if (paths[i]) paths[i].setAttribute('stroke-dashoffset', String((next * Math.PI / 180) * 50))
        return next
      })
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [goalsLen])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    isDraggingRef.current = true
    setIsDragging(true)
    dragStart.current = { x: e.clientX, y: e.clientY }
    offsetStart.current = { ...offset }
    e.stopPropagation()
  }, [offset])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDraggingRef.current) return
    const next = {
      x: offsetStart.current.x + (e.clientX - dragStart.current.x),
      y: offsetStart.current.y + (e.clientY - dragStart.current.y),
    }
    offsetRef.current = next
    setOffset(next)
  }, [])

  const handleMouseUp = useCallback(() => {
    isDraggingRef.current = false
    setIsDragging(false)
  }, [])

  const cx = 400, cy = 200
  const tx = offset.x, ty = offset.y

  return (
    <div
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{
        position: 'fixed', inset: 0, zIndex: Z.ARC_REACTOR, overflow: 'visible',
        pointerEvents: 'none', cursor: isDragging.current ? 'grabbing' : 'grab',
      }}
    >
      {/* ── ARC REACTOR ── */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: Z.ARC_REACTOR, overflow: 'visible',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transform: `translate(${tx}px, ${ty}px)`,
        transition: isDragging.current ? 'none' : 'transform 0.3s ease',
      }}>
        <div style={{ pointerEvents: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
          <div style={{
            width: 560, height: 560, borderRadius: '50%',
            background: `radial-gradient(circle, ${orbColor}06 0%, ${orbColor}03 40%, transparent 70%)`,
            filter: 'blur(60px)', transition: 'all 0.8s ease',
          }} />
          <div style={{
            position: 'absolute', width: glowRadius * 2, height: glowRadius * 2, borderRadius: '50%',
            background: `radial-gradient(circle, ${orbColor}15 0%, ${orbColor}08 50%, transparent 70%)`,
            filter: 'blur(20px)', transition: 'all 0.05s linear',
          }} />
          <svg style={{
            position: 'absolute', width: 800, height: 400, overflow: 'visible',
            filter: `drop-shadow(0 0 15px ${orbColor}44)`, transition: 'filter 0.8s ease',
          }} viewBox="0 0 800 400">
            <defs>
              <radialGradient id="cg"><stop offset="0%" stopColor="#fff" stopOpacity="1" />
                <stop offset="20%" stopColor="#fff" stopOpacity="0.8" />
                <stop offset="40%" stopColor={orbColor} stopOpacity="0.6" />
                <stop offset="70%" stopColor={orbColor} stopOpacity="0.15" />
                <stop offset="100%" stopColor={orbColor} stopOpacity="0" /></radialGradient>
              <filter id="cf"><feGaussianBlur stdDeviation="2" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
              <pattern id="hg" width="12" height="20.784" patternUnits="userSpaceOnUse">
                <path d="M6,0 L12,3.464 L12,10.392 L6,13.856 L0,10.392 L0,3.464 Z" fill="none" stroke={orbColor} strokeWidth="0.3" opacity="0.08" />
                <path d="M6,20.784 L12,17.32 L12,10.392" fill="none" stroke={orbColor} strokeWidth="0.3" opacity="0.08" /></pattern>
            </defs>
            <circle cx={cx} cy={cy} r={260} fill="url(#cg)" opacity="0.3" />
            <circle cx={cx} cy={cy} r={180} fill="url(#hg)" opacity="0.8" />
            {Array.from({ length: CROSSHAIR_COUNT }, (_, i) => {
              const a = (i * 360 / CROSSHAIR_COUNT) * Math.PI / 180
              const l = 160 + crosshairExtend
              return <line key={`ch-${i}`} x1={cx + Math.cos(a) * 30} y1={cy + Math.sin(a) * 30} x2={cx + Math.cos(a) * l} y2={cy + Math.sin(a) * l} stroke={orbColor} strokeWidth="0.5" opacity="0.2" />
            })}
            {Array.from({ length: 6 }, (_, i) => {
              const a = (i * 360 / 6) * Math.PI / 180
              return <polygon key={i} points={`${cx + Math.cos(a) * 30},${cy + Math.sin(a) * 30} ${cx + Math.cos(a) * 200},${cy + Math.sin(a) * 200} ${cx + Math.cos(a + 0.15) * 170},${cy + Math.sin(a + 0.15) * 170}`} fill="none" stroke={orbColor} strokeWidth="0.4" opacity="0.15" />
            })}
            {Array.from({ length: 6 }, (_, i) => {
              const a = (i * 360 / 6) * Math.PI / 180
              return <line key={i} x1={cx + Math.cos(a) * 30} y1={cy + Math.sin(a) * 30} x2={cx + Math.cos(a + Math.PI / 6) * 55} y2={cy + Math.sin(a + Math.PI / 6) * 55} stroke={orbColor} strokeWidth="0.6" opacity="0.2" />
            })}
            {Array.from({ length: PARTICLE_COUNT }, (_, i) => {
              const a = (i * 360 / PARTICLE_COUNT) * Math.PI / 180
              return <circle key={`p-${i}`} cx={cx + Math.cos(a) * PARTICLE_RADIUS} cy={cy + Math.sin(a) * PARTICLE_RADIUS} r="2" fill={orbColor} opacity="0.6">
                <animate attributeName="opacity" values="0.05;0.5;0.05" dur={`${2 + i * 0.5}s`} begin={`-${i * 0.7}s`} repeatCount="indefinite" /></circle>
            })}
            {isActive && Array.from({ length: 12 }, (_, i) => {
              const a = (i * 360 / 12) * Math.PI / 180
              return <line key={i} x1={cx + Math.cos(a) * 35} y1={cy + Math.sin(a) * 35} x2={cx + Math.cos(a) * (220 + Math.sin(Date.now() * 0.002 + i) * 40)} y2={cy + Math.sin(a) * (220 + Math.sin(Date.now() * 0.002 + i) * 40)} stroke={orbColor} strokeWidth="0.3" opacity="0.15">
                <animate attributeName="opacity" values="0.05;0.2;0.05" dur={`${1 + i * 0.2}s`} repeatCount="indefinite" /></line>
            })}
            <circle cx={cx} cy={cy} r={20} fill="#fff" filter="url(#cf)" opacity="0.95" />
            <circle cx={cx} cy={cy} r={10} fill="#fff" opacity="1" />
            <circle cx={cx} cy={cy} r={35} fill="none" stroke={orbColor} strokeWidth="1.5" opacity="0.3">
              {isActive && <animate attributeName="r" values="35;40;35" dur="2s" repeatCount="indefinite" />}
              {isActive && <animate attributeName="opacity" values="0.3;0.1;0.3" dur="2s" repeatCount="indefinite" />}</circle>
          </svg>
          <div style={{ position: 'absolute', width: 80, height: 80, borderRadius: '50%', background: `radial-gradient(circle, rgba(255,255,255,0.95) 0%, ${orbColor}88 40%, transparent 70%)`, boxShadow: `0 0 60px ${orbColor}66, 0 0 150px ${orbColor}33`, transition: 'all 0.8s ease' }} />
          <div style={{ position: 'absolute', width: 20, height: 20, borderRadius: '50%', background: 'rgba(255,255,255,1)', boxShadow: `0 0 20px ${orbColor}, 0 0 50px ${orbColor}88`, transition: 'all 0.8s ease' }} />
        </div>

        {/* ── CENTRAL HOLOGRAM RINGS ── */}
        <svg ref={svgRef} style={{ position: 'absolute', width: 800, height: 400, pointerEvents: 'none', overflow: 'visible' }}>
          {RINGS.map((ring, i) => (
            <ellipse key={i} className="holo-ring" cx={cx} cy={cy} rx={ring.rx} ry={ring.ry}
              fill="none" stroke={orbColor} strokeWidth="0.8" strokeDasharray="4 8" opacity={ring.opacity}
              style={{ transform: `rotateX(${ring.tilt}deg)`, transformOrigin: `${cx}px ${cy}px`, filter: `drop-shadow(0 0 4px ${orbColor})` }} />
          ))}
          <ellipse cx={cx} cy={cy} rx="360" ry="120" fill="none" stroke={orbColor} strokeWidth="0.3" opacity="0.06"
            style={{ transform: 'rotateX(5deg)', transformOrigin: `${cx}px ${cy}px` }} />
          {PARTICLE_RINGS.map((pr) => (
            <g key={pr.rx} style={{ transform: `rotateX(${pr.tilt}deg)`, transformOrigin: `${cx}px ${cy}px` }}>
              {Array.from({ length: pr.count }).map((_, j) => (
                <circle key={j} r="2" fill={orbColor} opacity="0.6">
                  <animateMotion dur={`${pr.dur}s`} repeatCount="indefinite" path={ellipsePath(cx, cy, pr.rx, pr.ry)} begin={`-${(j / pr.count) * pr.dur}s`} />
                </circle>
              ))}
            </g>
          ))}
        </svg>

        {/* ── NEURAL PATHWAYS ── */}
        <svg style={{ position: 'absolute', width: 800, height: 400, pointerEvents: 'none', overflow: 'visible' }}>
          {PATHWAYS.map((p, i) => {
            const rad = (p.angle * Math.PI) / 180
            const ex = cx + Math.cos(rad) * p.length, ey = cy + Math.sin(rad) * p.length
            return (
              <g key={i}>
                <line x1={cx} y1={cy} x2={ex} y2={ey} stroke={orbColor} strokeWidth="0.6" opacity={isActive ? 0.3 : 0.12} />
                {isActive && <circle cx={ex} cy={ey} r="2" fill={orbColor} opacity="0.5">
                  <animate attributeName="r" values="1;3;1" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.3;0.8;0.3" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" /></circle>}
                {Array.from({ length: p.branches }, (_, b) => {
                  const ba = rad + (b - (p.branches - 1) / 2) * 0.4
                  const bx = ex + Math.cos(ba) * p.length * 0.4, by = ey + Math.sin(ba) * p.length * 0.4
                  return <line key={b} x1={ex} y1={ey} x2={bx} y2={by} stroke={orbColor} strokeWidth="0.4" opacity={isActive ? 0.2 : 0.06} />
                })}
              </g>
            )
          })}
        </svg>

        {/* ── COMMUNICATION TRACES ── */}
        <svg style={{ position: 'absolute', width: '100vw', height: '100vh', pointerEvents: 'none', overflow: 'visible' }}>
          {TRACES.map((t, i) => {
            const fromX = t.side === 'left' ? '10%' : '90%'
            const toX = '50%'
            const midX = t.side === 'left' ? '30%' : '70%'
            const cyP = `calc(50% + ${t.yOff}px)`
            const d = `M ${fromX} ${cyP} Q ${midX} calc(${cyP} - 40px) ${toX} ${cyP}`
            return (
              <g key={i}>
                <path d={d} fill="none" stroke={orbColor} strokeWidth="0.5" opacity={isActive ? 0.2 : 0.06} strokeDasharray="4 6">
                  {isActive && <animate attributeName="stroke-dashoffset" from="20" to="0" dur={`${2 + i * 0.5}s`} repeatCount="indefinite" />}
                </path>
                {isActive && <circle r="2" fill={orbColor} opacity="0.6"><animateMotion dur={`${3 + i * 0.3}s`} repeatCount="indefinite" path={d} /></circle>}
              </g>
            )
          })}
        </svg>

        {/* ── RADIATION PULSE ── */}
        <svg style={{ position: 'absolute', width: 700, height: 700, left: '50%', top: '50%', transform: 'translate(-50%, -50%)', pointerEvents: 'none', overflow: 'visible' }}>
          {[...Array(8)].map((_, i) => (
            <circle
              key={i}
              cx={350} cy={350}
              r={10}
              fill="none"
              stroke={isActive ? '#81D4FA' : isAlert ? '#FF3D3D' : '#4FC3F7'}
              strokeWidth={0.8}
              opacity={0}
            >
              <animate attributeName="r" from="10" to="350" dur="5s" begin={`${i * 0.625}s`} repeatCount="indefinite" />
              <animate attributeName="opacity" from="0.2" to="0" dur="5s" begin={`${i * 0.625}s`} repeatCount="indefinite" />
              <animate attributeName="stroke-width" from="1.5" to="0.05" dur="5s" begin={`${i * 0.625}s`} repeatCount="indefinite" />
            </circle>
          ))}
        </svg>

        {/* ── DECORATIVE RINGS (bottom-left) ── */}
        <div style={{ position: 'absolute', bottom: -100, left: -750, width: 1000, height: 600, pointerEvents: 'none', overflow: 'hidden' }}>
          <svg viewBox="0 0 1000 600" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
            <ellipse cx={500} cy={300} rx={480} ry={180} fill="none" stroke={orbColor} strokeWidth={1} opacity={0.4}>
              <animateTransform attributeName="transform" type="rotate" from="0 500 300" to="360 500 300" dur="20s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx={500} cy={300} rx={360} ry={120} fill="none" stroke={orbColor} strokeWidth={1} opacity={0.3}>
              <animateTransform attributeName="transform" type="rotate" from="360 500 300" to="0 500 300" dur="15s" repeatCount="indefinite" />
            </ellipse>
            <ellipse cx={500} cy={300} rx={240} ry={80} fill="none" stroke={orbColor} strokeWidth={1} opacity={0.25}>
              <animateTransform attributeName="transform" type="rotate" from="0 500 300" to="360 500 300" dur="10s" repeatCount="indefinite" />
            </ellipse>
          </svg>
        </div>
      </div>
    </div>
  )
}
