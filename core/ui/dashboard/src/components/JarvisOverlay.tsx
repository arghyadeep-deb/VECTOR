import { useMemo } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'

/*
 * JARVIS HOLOGRAPHIC HUD CORNER BRACKETS
 * Four angular L-brackets frame the viewport like an Iron-Man helmet HUD.
 */

const BRACKET_LEN = 40
const BRACKET_THICK = 2
const COLOR = '#00CFFF'

const cornerPositions = [
  { top: 12, left: 12, rotate: 0 },        // top-left
  { top: 12, right: 12, rotate: 90 },      // top-right
  { bottom: 12, left: 12, rotate: 270 },   // bottom-left
  { bottom: 12, right: 12, rotate: 180 },  // bottom-right
] as const

function CornerBracket({ pos }: { pos: (typeof cornerPositions)[number] }) {
  const style: React.CSSProperties = {
    position: 'fixed',
    width: BRACKET_LEN,
    height: BRACKET_LEN,
    zIndex: Z.OVERLAY,
    pointerEvents: 'none',
    ...('top' in pos ? { top: pos.top } : { bottom: pos.bottom }),
    ...('left' in pos ? { left: pos.left } : { right: pos.right }),
    transform: `rotate(${pos.rotate}deg)`,
  }

  return (
    <svg style={style} viewBox={`0 0 ${BRACKET_LEN} ${BRACKET_LEN}`}>
      <path
        d={`M 0 ${BRACKET_THICK / 2} L ${BRACKET_LEN - BRACKET_THICK / 2} ${BRACKET_THICK / 2} L ${BRACKET_LEN - BRACKET_THICK / 2} ${BRACKET_LEN}`}
        fill="none"
        stroke={COLOR}
        strokeWidth={BRACKET_THICK}
        strokeOpacity={0.6}
      />
    </svg>
  )
}

/* Particle text scroller on top edge */
function ParticleText() {
  const text = 'VECTOR // JARVIS HUD // COGNITIVE ENGINE // ' + '0'.repeat(40)
  const chars = useMemo(() => text.split(''), [])

  return (
    <div
      style={{
        position: 'fixed',
        top: 8,
        left: 60,
        right: 60,
        height: 14,
        overflow: 'hidden',
        zIndex: Z.OVERLAY,
        pointerEvents: 'none',
        display: 'flex',
        justifyContent: 'center',
        gap: 2,
      }}
    >
      {chars.map((c, i) => (
        <span
          key={i}
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 8,
            color: Math.random() > 0.7 ? '#00CFFF' : '#002244',
            opacity: Math.random() > 0.8 ? 1 : 0.3,
          }}
        >
          {c}
        </span>
      ))}
    </div>
  )
}

export default function JarvisOverlay() {
  const status = useVectorStore((s) => s.status)

  return (
    <>
      {/* Corner brackets */}
      {cornerPositions.map((p, i) => (
        <CornerBracket key={i} pos={p} />
      ))}

      {/* Particle text */}
      <ParticleText />

      {/* Central reticle */}
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          width: 6,
          height: 6,
          marginLeft: -3,
          marginTop: -3,
          border: '1px solid rgba(0,207,255,0.3)',
          borderRadius: '50%',
          zIndex: Z.OVERLAY,
          pointerEvents: 'none',
        }}
      />

      {/* Bottom-center status hex */}
      <div
        style={{
          position: 'fixed',
          bottom: 46,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: Z.OVERLAY,
          pointerEvents: 'none',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
            color: '#00CFFF',
            letterSpacing: '0.15em',
          }}
        >
          {status?.vector_version ?? '...'}
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 8,
            color: '#00CFFF',
            opacity: 0.8,
          }}
        >
          {'<SYSTEM READY>'}
        </span>
      </div>
    </>
  )
}
