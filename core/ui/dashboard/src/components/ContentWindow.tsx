import { useEffect, useState } from 'react'
import { useVectorStore, ContentWindowEntry } from '../store/vectorStore'
import CameraView from './CameraView'
import MapView from './MapView'
import { getWidget } from '../widgets/registry'

function SingleWindow({ w, index }: { w: ContentWindowEntry; index: number }) {
  const removeContentWindow = useVectorStore((s) => s.removeContentWindow)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
  }, [])

  const close = () => {
    setVisible(false)
    setTimeout(() => removeContentWindow(w.id), 400)
  }

  // Camera fills the entire screen — orb stays visible in corner
  if (w.type === 'camera') {
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 185,
        background: '#000',
        transform: visible ? 'scale(1)' : 'scale(0.97)',
        opacity: visible ? 1 : 0,
        transition: 'transform 0.4s ease, opacity 0.4s ease',
        overflow: 'hidden',
      }}>
        {/* Invisible close zone — top-right corner tap/click, no visible chrome (matches reference) */}
        <div
          onClick={close}
          title="Click to close camera"
          style={{
            position: 'absolute', top: 0, right: 0, width: 60, height: 60,
            zIndex: 10, cursor: 'pointer',
          }}
        />
        <CameraView windowId={w.id} />
      </div>
    )
  }

  // Staggered layout matching reference: large main + small secondary + small tertiary
  const positions: React.CSSProperties[] = [
    { top: 40, left: 0, width: '70vw', maxHeight: '75vh' },
    { bottom: 60, right: 0, width: '32vw', maxHeight: '38vh' },
    { top: 40, right: 0, width: '30vw', maxHeight: '45vh' },
  ]
  const pos = positions[index % positions.length]

  return (
    <div style={{
      position: 'fixed',
      ...pos,
      zIndex: 190,
      background: 'rgba(2, 8, 18, 0.92)',
      backdropFilter: 'blur(18px)',
      WebkitBackdropFilter: 'blur(18px)',
      border: '1px solid rgba(0,207,255,0.18)',
      boxShadow: '0 0 40px rgba(0,207,255,0.06)',
      transform: visible ? 'translateY(0)' : 'translateY(-24px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.4s cubic-bezier(0.4,0,0.2,1), opacity 0.4s ease',
      overflow: 'hidden',
    }}>
      {/* Header — minimal, matches reference */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '5px 12px',
        borderBottom: '1px solid rgba(0,207,255,0.08)',
        background: 'rgba(0,207,255,0.03)',
      }}>
        <span style={{
          fontFamily: "'Orbitron', sans-serif",
          fontSize: 9,
          color: 'rgba(0,207,255,0.65)',
          letterSpacing: '0.18em',
        }}>
          {w.title.toUpperCase()}
        </span>
        <button onClick={close} style={{
          background: 'none', border: 'none',
          color: 'rgba(0,207,255,0.4)',
          fontFamily: "'Orbitron', sans-serif", fontSize: 9,
          padding: '0 4px', cursor: 'pointer', letterSpacing: '0.08em',
        }}>
          ✕
        </button>
      </div>

      {/* Content */}
      <div style={{ padding: '10px 14px', overflow: 'auto', maxHeight: 'calc(100% - 30px)' }}>
        {/* Registry widgets take priority — id-based lookup so voice
            "open music" / "open schematic search" etc. render the right
            component without any extra wiring. */}
        {(() => {
          const spec = getWidget(w.id)
          if (spec) {
            const C = spec.component
            return <C onClose={close} />
          }
          return null
        })()}
        {!getWidget(w.id) && w.type === 'text' && (
          <div style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 13,
            color: '#c0ddf0',
            lineHeight: 1.75,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            <span style={{ color: '#00CFFF', fontFamily: "'Orbitron', sans-serif", fontSize: 9, letterSpacing: '0.1em' }}>
              VECTOR{' '}
            </span>
            {w.content}
          </div>
        )}
        {!getWidget(w.id) && w.type === 'map' && <MapView />}
      </div>
    </div>
  )
}

export default function ContentWindowManager() {
  const windows = useVectorStore((s) => s.contentWindows)

  return (
    <>
      {windows.map((w, i) => (
        <SingleWindow key={w.id} w={w} index={i} />
      ))}
    </>
  )
}
