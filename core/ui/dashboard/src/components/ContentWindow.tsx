import { useEffect, useState } from 'react'
import { useVectorStore, ContentWindowEntry } from '../store/vectorStore'
import CameraView from './CameraView'
import MapView from './MapView'

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

  // Staggered positioning: first window top-left area, second bottom-right area
  const positions: React.CSSProperties[] = [
    { top: 60, left: 16, width: '55vw', maxHeight: '65vh' },
    { bottom: 110, right: 110, width: '32vw', maxHeight: '40vh' },
    { top: 60, right: 16, width: '30vw', maxHeight: '50vh' },
  ]
  const pos = positions[index % positions.length]

  return (
    <div style={{
      position: 'fixed',
      ...pos,
      zIndex: 190,
      background: 'rgba(2, 10, 20, 0.94)',
      backdropFilter: 'blur(16px)',
      WebkitBackdropFilter: 'blur(16px)',
      border: '1px solid rgba(0,207,255,0.25)',
      boxShadow: '0 0 40px rgba(0,207,255,0.08), inset 0 0 40px rgba(0,207,255,0.03)',
      transform: visible ? 'translateY(0)' : 'translateY(-30px)',
      opacity: visible ? 1 : 0,
      transition: 'transform 0.4s cubic-bezier(0.4,0,0.2,1), opacity 0.4s ease',
      overflow: 'hidden',
    }}>
      {/* Corner brackets */}
      <div style={{ position: 'absolute', top: 0, left: 0, width: 16, height: 16, borderTop: '2px solid rgba(0,207,255,0.6)', borderLeft: '2px solid rgba(0,207,255,0.6)' }} />
      <div style={{ position: 'absolute', top: 0, right: 0, width: 16, height: 16, borderTop: '2px solid rgba(0,207,255,0.6)', borderRight: '2px solid rgba(0,207,255,0.6)' }} />
      <div style={{ position: 'absolute', bottom: 0, left: 0, width: 16, height: 16, borderBottom: '2px solid rgba(0,207,255,0.6)', borderLeft: '2px solid rgba(0,207,255,0.6)' }} />
      <div style={{ position: 'absolute', bottom: 0, right: 0, width: 16, height: 16, borderBottom: '2px solid rgba(0,207,255,0.6)', borderRight: '2px solid rgba(0,207,255,0.6)' }} />

      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '6px 12px',
        borderBottom: '1px solid rgba(0,207,255,0.12)',
        background: 'rgba(0,207,255,0.04)',
      }}>
        <span style={{
          fontFamily: "'Orbitron', sans-serif",
          fontSize: 10,
          color: '#00CFFF',
          letterSpacing: '0.15em',
        }}>
          {w.title.toUpperCase()}
        </span>
        <button
          onClick={close}
          style={{
            background: 'none',
            border: '1px solid rgba(0,207,255,0.3)',
            color: 'rgba(0,207,255,0.7)',
            fontFamily: "'Orbitron', sans-serif",
            fontSize: 9,
            padding: '1px 6px',
            cursor: 'pointer',
            letterSpacing: '0.1em',
          }}
        >
          CLOSE
        </button>
      </div>

      {/* Content */}
      <div style={{ padding: 12, overflow: 'auto', maxHeight: 'calc(100% - 36px)' }}>
        {w.type === 'text' && (
          <div style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 13,
            color: '#c8e8ff',
            lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            <span style={{ color: '#00CFFF', fontFamily: "'Orbitron', sans-serif", fontSize: 10 }}>VECTOR: </span>
            {w.content}
          </div>
        )}
        {w.type === 'camera' && <CameraView windowId={w.id} />}
        {w.type === 'map' && <MapView />}
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
