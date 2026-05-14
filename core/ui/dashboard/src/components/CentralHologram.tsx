import { useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

const RINGS = [
  { rx: 320, ry: 80, tilt: 10, speed: 0.2, opacity: 0.15 },
  { rx: 260, ry: 100, tilt: -15, speed: -0.3, opacity: 0.12 },
  { rx: 200, ry: 60, tilt: 25, speed: 0.25, opacity: 0.18 },
  { rx: 150, ry: 50, tilt: -5, speed: -0.35, opacity: 0.15 },
]

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
          key={i}
          cx="400" cy="200"
          rx={ring.rx} ry={ring.ry}
          fill="none"
          stroke="var(--theme-accent, #00d4ff)"
          strokeWidth="0.8"
          strokeDasharray="4 8"
          opacity={ring.opacity}
          style={{
            transform: `rotateX(${ring.tilt}deg)`,
            transformOrigin: '400px 200px',
            filter: `drop-shadow(0 0 4px var(--theme-accent, #00d4ff))`,
            transition: 'stroke 0.8s ease',
          }}
        />
      ))}
      {/* Outer glow ring */}
      <ellipse
        cx="400" cy="200" rx="360" ry="120"
        fill="none" stroke="var(--theme-accent, #00d4ff)"
        strokeWidth="0.3" opacity="0.06"
        style={{ transform: 'rotateX(5deg)', transformOrigin: '400px 200px' }}
      />
    </svg>
  )
}