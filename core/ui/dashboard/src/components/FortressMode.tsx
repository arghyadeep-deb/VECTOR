import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

const CYAN = '#00CFFF'
const BG = '#000815'
const MONO = "'JetBrains Mono', monospace"
const ORBITRON = "'Orbitron', sans-serif"

// ── Network background canvas ────────────────────────────────────────────────

function FortressBg() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight

    // 30 random nodes
    const nodes = Array.from({ length: 30 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
    }))

    let raf = 0
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = BG
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // Move nodes
      nodes.forEach(n => {
        n.x += n.vx
        n.y += n.vy
        if (n.x < 0 || n.x > canvas.width) n.vx *= -1
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1
      })

      // Draw triangulated connections (connect each node to 2 nearest)
      nodes.forEach((n, i) => {
        const sorted = nodes
          .map((o, j) => ({ j, dist: Math.hypot(o.x - n.x, o.y - n.y) }))
          .filter(({ j }) => j !== i)
          .sort((a, b) => a.dist - b.dist)
          .slice(0, 2)

        sorted.forEach(({ j, dist }) => {
          if (dist > 280) return
          const alpha = (1 - dist / 280) * 0.18
          ctx.beginPath()
          ctx.moveTo(n.x, n.y)
          ctx.lineTo(nodes[j].x, nodes[j].y)
          ctx.strokeStyle = `rgba(0,207,255,${alpha})`
          ctx.lineWidth = 0.7
          ctx.stroke()
        })

        // Node dot
        ctx.beginPath()
        ctx.arc(n.x, n.y, 2.5, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(0,207,255,0.4)`
        ctx.fill()
      })

      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <canvas ref={canvasRef} style={{
      position: 'absolute', inset: 0, width: '100%', height: '100%',
    }} />
  )
}

// ── Gear stack SVG ───────────────────────────────────────────────────────────

function GearStack() {
  return (
    <div style={{ position: 'relative', width: 300, height: 520 }}>
      <style>{`
        @keyframes gearCW   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes gearCCW  { from{transform:rotate(0deg)} to{transform:rotate(-360deg)} }
        @keyframes gearSlow { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes glow-pulse { 0%,100%{filter:drop-shadow(0 0 6px #00CFFF)} 50%{filter:drop-shadow(0 0 18px #00CFFF)} }
      `}</style>
      <svg width={300} height={520} style={{ overflow: 'visible', filter: 'drop-shadow(0 0 10px #00CFFF55)' }}>
        {/* Vertical shaft */}
        <line x1={150} y1={30} x2={150} y2={490} stroke={CYAN} strokeWidth={2} opacity={0.25} />

        {/* Top hexagonal gear */}
        <g style={{ transformOrigin: '150px 110px', animation: 'gearCW 12s linear infinite' }}>
          {Array.from({ length: 6 }).map((_, i) => {
            const a = (i / 6) * Math.PI * 2 - Math.PI / 6
            const x = 150 + 70 * Math.cos(a)
            const y = 110 + 70 * Math.sin(a)
            return <circle key={i} cx={x} cy={y} r={8} fill="none" stroke={CYAN} strokeWidth={1.5} opacity={0.6} />
          })}
          <polygon points={Array.from({ length: 6 }).map((_, i) => {
            const a = (i / 6) * Math.PI * 2 - Math.PI / 6
            return `${150 + 65 * Math.cos(a)},${110 + 65 * Math.sin(a)}`
          }).join(' ')} fill="none" stroke={CYAN} strokeWidth={2} opacity={0.7} />
          <circle cx={150} cy={110} r={30} fill="none" stroke={CYAN} strokeWidth={1.5} opacity={0.5} />
          <circle cx={150} cy={110} r={10} fill={CYAN} opacity={0.4} />
        </g>

        {/* Gear teeth top */}
        {Array.from({ length: 18 }).map((_, i) => {
          const a = (i / 18) * Math.PI * 2
          const x1 = 150 + 65 * Math.cos(a); const y1 = 110 + 65 * Math.sin(a)
          const x2 = 150 + 78 * Math.cos(a); const y2 = 110 + 78 * Math.sin(a)
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={CYAN} strokeWidth={3} opacity={0.35} />
        })}

        {/* Middle circular gear */}
        <g style={{ transformOrigin: '150px 265px', animation: 'gearCCW 8s linear infinite' }}>
          <circle cx={150} cy={265} r={75} fill="none" stroke={CYAN} strokeWidth={2} opacity={0.6} />
          <circle cx={150} cy={265} r={50} fill="none" stroke={CYAN} strokeWidth={1} opacity={0.35}
            strokeDasharray="6 4" />
          <circle cx={150} cy={265} r={22} fill="none" stroke={CYAN} strokeWidth={1.5} opacity={0.5} />
          <circle cx={150} cy={265} r={8} fill={CYAN} opacity={0.5} />
          {/* Gear spokes */}
          {Array.from({ length: 6 }).map((_, i) => {
            const a = (i / 6) * Math.PI * 2
            return <line key={i} x1={150 + 22 * Math.cos(a)} y1={265 + 22 * Math.sin(a)}
              x2={150 + 50 * Math.cos(a)} y2={265 + 50 * Math.sin(a)}
              stroke={CYAN} strokeWidth={2} opacity={0.4} />
          })}
        </g>

        {/* Middle gear teeth */}
        {Array.from({ length: 24 }).map((_, i) => {
          const a = (i / 24) * Math.PI * 2
          const x1 = 150 + 72 * Math.cos(a); const y1 = 265 + 72 * Math.sin(a)
          const x2 = 150 + 85 * Math.cos(a); const y2 = 265 + 85 * Math.sin(a)
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={CYAN} strokeWidth={4} opacity={0.3} />
        })}

        {/* JARVIS text in gear */}
        <text x={150} y={270} textAnchor="middle"
          fontFamily={ORBITRON} fontSize={14} fontWeight="700"
          letterSpacing="0.2em" fill={CYAN} opacity={0.8}>
          VECTOR
        </text>

        {/* Bottom hex gear */}
        <g style={{ transformOrigin: '150px 420px', animation: 'gearSlow 15s linear infinite' }}>
          {Array.from({ length: 6 }).map((_, i) => {
            const a = (i / 6) * Math.PI * 2
            const x = 150 + 55 * Math.cos(a)
            const y = 420 + 55 * Math.sin(a)
            return <circle key={i} cx={x} cy={y} r={6} fill="none" stroke={CYAN} strokeWidth={1.2} opacity={0.5} />
          })}
          <polygon points={Array.from({ length: 6 }).map((_, i) => {
            const a = (i / 6) * Math.PI * 2
            return `${150 + 52 * Math.cos(a)},${420 + 52 * Math.sin(a)}`
          }).join(' ')} fill="none" stroke={CYAN} strokeWidth={1.5} opacity={0.6} />
          <circle cx={150} cy={420} r={22} fill="none" stroke={CYAN} strokeWidth={1} opacity={0.4} />
          <circle cx={150} cy={420} r={8} fill={CYAN} opacity={0.35} />
        </g>

        {/* Bottom data label */}
        <text x={150} y={510} textAnchor="middle"
          fontFamily={MONO} fontSize={8} letterSpacing="0.2em" fill={CYAN} opacity={0.4}>
          - 0000002
        </text>
        <text x={150} y={524} textAnchor="middle"
          fontFamily={MONO} fontSize={7} letterSpacing="0.1em" fill={CYAN} opacity={0.25}>
          LOAD: 6000T
        </text>
      </svg>
    </div>
  )
}

// ── NODE panel with waveform ─────────────────────────────────────────────────

function NodePanel({ id, cpu, mem }: { id: string; cpu: number; mem: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const frameRef = useRef(0)
  const dataRef = useRef<number[]>(Array.from({ length: 40 }, () => Math.random()))

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    let raf = 0

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      const w = canvas.width / dataRef.current.length
      dataRef.current.forEach((v, i) => {
        const barH = v * canvas.height * 0.85
        ctx.fillStyle = `rgba(0,207,255,${0.3 + v * 0.5})`
        ctx.fillRect(i * w, canvas.height - barH, w - 1, barH)
      })

      // Slowly evolve waveform
      frameRef.current++
      if (frameRef.current % 4 === 0) {
        dataRef.current.shift()
        dataRef.current.push(0.3 + Math.random() * 0.5 + Math.sin(frameRef.current * 0.1) * 0.2)
      }
      raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <div style={{
      background: 'rgba(0,12,28,0.8)',
      border: `1px solid rgba(0,207,255,0.2)`,
      padding: '8px 10px',
      marginBottom: 8,
      width: 200,
    }}>
      <div style={{ fontFamily: ORBITRON, fontSize: 8, color: CYAN, letterSpacing: '0.2em', marginBottom: 4 }}>
        NODE-{id}
        <span style={{ float: 'right', color: 'rgba(0,207,255,0.4)', fontFamily: MONO, fontSize: 7 }}>DIAGNOSTIC</span>
      </div>
      <canvas ref={canvasRef} width={180} height={28} style={{ display: 'block', marginBottom: 4 }} />
      <div style={{ fontFamily: MONO, fontSize: 7.5, color: 'rgba(0,207,255,0.55)', lineHeight: 1.7 }}>
        <div>SYSTEM LOAD: {cpu.toFixed(0)}%</div>
        <div>SYSTEM MEM: {mem.toFixed(0)}%</div>
        <div>SYSTEM LOG: {new Date().toLocaleTimeString()}</div>
      </div>
    </div>
  )
}

// ── Scrolling diagnostics ────────────────────────────────────────────────────

function DiagnosticsPanel() {
  const [lines, setLines] = useState<string[]>([
    'SYSTEM DIAGNOSTICS: NOMINAL',
    'CORE TEMP: OPTIMAL',
    'CORE TEMP: OPTIMAL',
    'SYSTEM CAUTION: NOMINAL',
    'CORE: COGNOSTIMAL',
    'CODE MARK VII PROTOCOL...',
    'LOAD MARK VII PROTOCOL...',
    'CODE STERISTT OCOCCC',
    'CODE STAMSTT TOGSI',
    'LOAD MARK VII PROTOCOL...',
    'CODE STERISTT SAN',
    'CODE STEBILIT BUICK',
    'LOAD MARK VII PROTOCOL...',
    'CODE SEABLITY PROTOCOL...',
    'CODE CEGNOUNIN POOSSOOT',
    'SRV:',
    'LOAD MARK VII PROTOCOL...',
    'CODE MARK VII PR. PROTOCOL',
    'CODE GOOSDH ICK',
    'CODE STEEK VII PROTOCOL...',
    'CODE STERISTT OCOCCC...',
    'CODE STEMLIIT UCUCCC...',
    'CODE STREIST',
    'CODE STEEK VII PROTOCOL...',
    'CODE SISRK VII PROTOKOOL',
    'CODE STEILITY QUECK...',
    'CODE STREAFIER',
    'CODE CAANDAM POOTSOOT 98%',
    'CODE MARK VII PROTOCOL...',
    'CODE SEARDJAMP PROTOCOL',
    'CODE TEMPORHIIR',
    'LOAD MAR PLOTOORBA 90K ROYES',
    'CORE: SEXPMANIK',
    'CODE TEAT NAME: SENSTYOR 80CK',
    'CODE TEAT WINE: SENETOIR 50RS',
    'CODE TEAT WINAS: SENETRIK 50ROK',
    'CODGCANNINONA',
    'CODE ROIN COMBLANSTYS DY TOSOK',
    'CODE: DORCOANNIS',
    'CODE: YOM CONMAG ANSTRADY TOSOK',
    'COROGANNANIS',
    'LONG MARK VII PROTOCOL...',
    'CORE: YOW CANVAS ANTVEGHIRIOIS',
    'CORE TEMP: OPTIMAL',
    'LOAD MAS DEPEKUANSFYOSY TOSIK',
    'CORE WINHOSE',
    'CODE: COM CANVAS ASCGORONONOL',
    'CODE: TEXT SION A',
  ])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const s = await api.status()
        const count = s.agents?.count ?? '—'
        const uptime = s.uptime_seconds ?? 0
        const h = Math.floor(uptime / 3600), m = Math.floor((uptime % 3600) / 60)
        setLines(prev => [...prev.slice(-60),
          `UPTIME: ${h}h ${m}m | AGENTS: ${count} | LOOP: ${s.loop_running ? 'ACTIVE' : 'STANDBY'}`,
        ])
      } catch {
        setLines(prev => [...prev.slice(-60), `PING: ${new Date().toLocaleTimeString()}`])
      }
    }, 4000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [lines])

  return (
    <div style={{ height: '100%', overflowY: 'auto', scrollbarWidth: 'none' }}>
      <div style={{ fontFamily: ORBITRON, fontSize: 8, color: CYAN, letterSpacing: '0.2em', marginBottom: 6, opacity: 0.7 }}>
        SYSTEM DIAGNOSTICS:
      </div>
      {lines.map((l, i) => (
        <div key={i} style={{
          fontFamily: MONO, fontSize: 8.5, lineHeight: 1.7,
          color: i === lines.length - 1 ? CYAN : 'rgba(0,207,255,0.45)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {l}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

// ── Main FortressMode ────────────────────────────────────────────────────────

export default function FortressMode() {
  const [stats, setStats] = useState({ cpu: 35, mem: 45 })

  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const s = await api.status()
        const agents = s.agents?.count ?? 0
        setStats({ cpu: 20 + agents * 2 + Math.random() * 10, mem: 30 + Math.random() * 20 })
      } catch {
        setStats(prev => ({ cpu: prev.cpu + (Math.random() - 0.5) * 5, mem: prev.mem + (Math.random() - 0.5) * 3 }))
      }
    }, 3000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: BG, overflow: 'hidden',
    }}>
      <FortressBg />

      {/* Top label */}
      <div style={{
        position: 'absolute', top: 12, left: 16,
        fontFamily: ORBITRON, fontSize: 10, color: CYAN,
        letterSpacing: '0.25em', opacity: 0.6,
      }}>
        VECTOR SCALE: INF.
      </div>

      {/* Main layout: 3 columns */}
      <div style={{
        position: 'absolute',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        display: 'flex', alignItems: 'center', gap: 40,
        width: 'calc(100vw - 80px)',
        maxWidth: 1200,
      }}>
        {/* Left: NODE panels */}
        <div style={{ flexShrink: 0 }}>
          <NodePanel id="A1" cpu={stats.cpu} mem={stats.mem} />
          <NodePanel id="A2" cpu={stats.mem} mem={stats.cpu * 0.8} />
        </div>

        {/* Center: gear stack */}
        <div style={{ flex: '0 0 300px', display: 'flex', justifyContent: 'center' }}>
          <GearStack />
        </div>

        {/* Right: diagnostics */}
        <div style={{
          flex: 1, minWidth: 240, maxWidth: 320,
          height: 480, padding: '8px 4px',
        }}>
          <DiagnosticsPanel />
        </div>
      </div>

      {/* Bottom progress bar */}
      <div style={{
        position: 'absolute', bottom: 50, left: '50%', transform: 'translateX(-50%)',
        width: 200, textAlign: 'center',
      }}>
        <div style={{ fontFamily: MONO, fontSize: 7.5, color: 'rgba(0,207,255,0.4)', letterSpacing: '0.1em', marginBottom: 4 }}>
          LOAD: {Math.round(stats.cpu)}T  VERBOSITY: TRAIL
        </div>
        <div style={{ height: 4, background: 'rgba(0,207,255,0.1)', borderRadius: 2 }}>
          <div style={{
            width: `${Math.min(stats.cpu * 2, 100)}%`, height: '100%',
            background: CYAN, borderRadius: 2, opacity: 0.7,
            transition: 'width 1s ease',
          }} />
        </div>
      </div>

      {/* Footer */}
      <div style={{
        position: 'absolute', bottom: 16, left: 0, right: 0,
        textAlign: 'center',
        fontFamily: ORBITRON, fontSize: 9,
        letterSpacing: '0.3em', color: CYAN, opacity: 0.35,
      }}>
        VECTOR GLOBAL NETWORK INTEGRITY
      </div>

      {/* Bottom-left scale label */}
      <div style={{
        position: 'absolute', bottom: 12, left: 16,
        fontFamily: ORBITRON, fontSize: 8, color: CYAN, opacity: 0.4, letterSpacing: '0.2em',
      }}>
        VECTOR SCALE: INF.
      </div>
    </div>
  )
}
