import { useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

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

export default function NeuralPathways() {
  const svgRef = useRef<SVGSVGElement>(null)
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)

  const cx = 400
  const cy = 200
  const isActive = goalsLen > 0

  return (
    <svg
      ref={svgRef}
      style={{
        position: 'fixed', top: '50%', left: '50%', zIndex: Z.HOLOGRAM + 1,
        width: 800, height: 400, marginLeft: -400, marginTop: -200,
        pointerEvents: 'none', overflow: 'visible',
      }}
    >
      {PATHWAYS.map((p, i) => {
        const rad = (p.angle * Math.PI) / 180
        const endX = cx + Math.cos(rad) * p.length
        const endY = cy + Math.sin(rad) * p.length

        const branchPaths = Array.from({ length: p.branches }, (_, b) => {
          const bAngle = rad + (b - (p.branches - 1) / 2) * 0.4
          const bLen = p.length * 0.4
          const bx = endX + Math.cos(bAngle) * bLen
          const by = endY + Math.sin(bAngle) * bLen
          return { x: bx, y: by }
        })

        return (
          <g key={i} style={{ transition: 'opacity 0.8s ease' }}>
            {/* Main pathway */}
            <line
              x1={cx} y1={cy} x2={endX} y2={endY}
              stroke="var(--theme-accent, #4FC3F7)"
              strokeWidth="0.6"
              opacity={isActive ? 0.3 : 0.12}
              style={{ transition: 'opacity 0.8s ease, stroke 0.8s ease' }}
            />
            {isActive && (
              <circle cx={endX} cy={endY} r="2" fill="var(--theme-accent, #4FC3F7)" opacity="0.5">
                <animate attributeName="r" values="1;3;1" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.3;0.8;0.3" dur={`${1.5 + i * 0.3}s`} repeatCount="indefinite" />
              </circle>
            )}
            {/* Branches */}
            {branchPaths.map((b, bi) => (
              <line
                key={bi}
                x1={endX} y1={endY} x2={b.x} y2={b.y}
                stroke="var(--theme-accent, #4FC3F7)"
                strokeWidth="0.4"
                opacity={isActive ? 0.2 : 0.06}
                style={{ transition: 'opacity 0.8s ease, stroke 0.8s ease' }}
              />
            ))}
          </g>
        )
      })}
    </svg>
  )
}