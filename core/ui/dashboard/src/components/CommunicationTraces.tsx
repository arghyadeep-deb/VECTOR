import { useRef, useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

const TRACES = [
  { side: 'left', yOff: -60, label: 'TELEMETRY' },
  { side: 'left', yOff: 0, label: 'COMMAND' },
  { side: 'left', yOff: 60, label: 'EVENTS' },
  { side: 'right', yOff: -80, label: 'DISTRICTS' },
  { side: 'right', yOff: 0, label: 'COUNCIL' },
  { side: 'right', yOff: 80, label: 'ANALYTICS' },
]

export default function CommunicationTraces() {
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)
  const isActive = goalsLen > 0

  return (
    <svg
      style={{
        position: 'fixed', inset: 0, zIndex: Z.HOLOGRAM + 2,
        width: '100%', height: '100%', pointerEvents: 'none',
        overflow: 'visible',
      }}
    >
      {TRACES.map((t, i) => {
        const fromX = t.side === 'left' ? '10%' : '90%'
        const toX = '50%'
        const midX = t.side === 'left' ? '30%' : '70%'
        const cy = `calc(50% + ${t.yOff}px)`

        const d = `M ${fromX} ${cy} Q ${midX} calc(${cy} - 40px) ${toX} ${cy}`

        return (
          <g key={i}>
            <path
              d={d}
              fill="none"
              stroke="var(--theme-accent, #4FC3F7)"
              strokeWidth="0.5"
              opacity={isActive ? 0.2 : 0.06}
              strokeDasharray="4 6"
              style={{ transition: 'opacity 0.8s ease, stroke 0.8s ease' }}
            >
              {isActive && (
                <animate attributeName="stroke-dashoffset" from="20" to="0" dur={`${2 + i * 0.5}s`} repeatCount="indefinite" />
              )}
            </path>
            {isActive && (
              <circle r="2" fill="var(--theme-accent, #4FC3F7)" opacity="0.6">
                <animateMotion dur={`${3 + i * 0.3}s`} repeatCount="indefinite" path={d} />
              </circle>
            )}
          </g>
        )
      })}
    </svg>
  )
}