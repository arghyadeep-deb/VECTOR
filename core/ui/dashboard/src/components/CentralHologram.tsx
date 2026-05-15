import { useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

const RINGS = [
  { rx: 320, ry: 80, tilt: 10, speed: 0.2, opacity: 0.15 },
  { rx: 260, ry: 100, tilt: -15, speed: -0.3, opacity: 0.12 },
  { rx: 200, ry: 60, tilt: 25, speed: 0.25, opacity: 0.18 },
  { rx: 150, ry: 50, tilt: -5, speed: -0.35, opacity: 0.15 },
]

const CX = 400, CY = 200

// Orbiting agent particles: 3 rings, 3/4/5 dots each
const PARTICLE_RINGS = [
  { rx: 345, ry: 115, count: 3, dur: 18, tilt: 8 },
  { rx: 275, ry: 85,  count: 4, dur: 14, tilt: -12 },
  { rx: 195, ry: 58,  count: 5, dur: 10, tilt: 20 },
]

function ellipsePath(cx: number, cy: number, rx: number, ry: number): string {
  return `M ${cx - rx},${cy} A ${rx},${ry} 0 1,1 ${cx + rx},${cy} A ${rx},${ry} 0 1,1 ${cx - rx},${cy}`
}

export default function CentralHologram() {
  const svgRef = useRef<SVGSVGElement>(null)
  const anglesRef = useRef(RINGS.map(() => 0))
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)

  useEffect(() => {
    if (!svgRef.current) return
    const paths = svgRef.current.querySelectorAll('ellipse')
    let raf = 0

    const speedMult = goalsLen > 0 ? 2.5 : 1

    const animate = () => {
      anglesRef.current = anglesRef.current.map((a, i) => {
        const next = a + RINGS[i].speed * speedMult
        if (paths[i]) {
          const rad = (next * Math.PI) / 180
          paths[i].setAttribute('stroke-dashoffset', String(rad * 50))
        }
        return next
      })
      raf = requestAnimationFrame(animate)
    }
    raf = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(raf)
  }, [goalsLen])

  return (
    <svg
      ref={svgRef}
      style={{
        position: 'fixed', top: '50%', left: '50%', zIndex: Z.HOLOGRAM,
        width: 800, height: 400, marginLeft: -400, marginTop: -200,
        pointerEvents: 'none', overflow: 'visible',
        transformStyle: 'preserve-3d', perspective: 800,
      }}
    >
      {RINGS.map((ring, i) => (
        <ellipse
          key={`ring-${i}`}
          cx={CX} cy={CY}
          rx={ring.rx} ry={ring.ry}
          fill="none"
          stroke="var(--theme-accent, #4FC3F7)"
          strokeWidth="0.8"
          strokeDasharray="4 8"
          opacity={ring.opacity}
          style={{
            transform: `rotateX(${ring.tilt}deg)`,
            transformOrigin: `${CX}px ${CY}px`,
            filter: `drop-shadow(0 0 4px var(--theme-accent, #4FC3F7))`,
            transition: 'stroke 0.8s ease',
          }}
        />
      ))}
      {/* Outer glow ring */}
      <ellipse
        cx={CX} cy={CY} rx="360" ry="120"
        fill="none" stroke="var(--theme-accent, #4FC3F7)"
        strokeWidth="0.3" opacity="0.06"
        style={{ transform: 'rotateX(5deg)', transformOrigin: `${CX}px ${CY}px` }}
      />

      {/* Orbiting agent particles — 12 dots on 3 rings */}
      {PARTICLE_RINGS.map((pr) => (
        <g key={`pr-${pr.rx}`} style={{ transform: `rotateX(${pr.tilt}deg)`, transformOrigin: `${CX}px ${CY}px` }}>
          {Array.from({ length: pr.count }).map((_, j) => (
            <circle key={`p-${pr.rx}-${j}`} r="2" fill="#4FC3F7" opacity="0.6">
              <animateMotion
                dur={`${pr.dur}s`}
                repeatCount="indefinite"
                path={ellipsePath(CX, CY, pr.rx, pr.ry)}
                begin={`-${(j / pr.count) * pr.dur}s`}
              />
            </circle>
          ))}
        </g>
      ))}
    </svg>
  )
}
