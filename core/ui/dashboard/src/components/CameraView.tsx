import { useEffect, useRef, useState } from 'react'
import { useVectorStore } from '../store/vectorStore'

interface Detection { label: string; confidence: number; bbox: [number, number, number, number] }
interface CameraFrame { frame: string; detections: Detection[]; width: number; height: number }

export default function CameraView({ windowId }: { windowId: string }) {
  const removeContentWindow = useVectorStore((s) => s.removeContentWindow)
  const imgRef = useRef<HTMLImageElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const [detections, setDetections] = useState<Detection[]>([])
  const [frameSize, setFrameSize] = useState({ w: 640, h: 480 })
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/camera/ws`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setError('Camera connection failed')

    ws.onmessage = (e) => {
      try {
        const data: CameraFrame = JSON.parse(e.data)
        if (imgRef.current) {
          imgRef.current.src = `data:image/jpeg;base64,${data.frame}`
        }
        setDetections(data.detections ?? [])
        if (data.width && data.height) setFrameSize({ w: data.width, h: data.height })
      } catch {
        // binary frame fallback
        if (e.data instanceof Blob && imgRef.current) {
          imgRef.current.src = URL.createObjectURL(e.data)
        }
      }
    }

    return () => ws.close()
  }, [])

  const [imgNaturalSize, setImgNaturalSize] = useState({ w: 640, h: 480 })
  const containerRef = useRef<HTMLDivElement>(null)

  const scaleX = containerRef.current ? containerRef.current.clientWidth / imgNaturalSize.w : 1
  const scaleY = containerRef.current ? containerRef.current.clientHeight / imgNaturalSize.h : 1

  return (
    <div style={{ position: 'relative', width: '100%' }} ref={containerRef}>
      {/* Status bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '3px 0 6px',
        fontFamily: "'Orbitron', sans-serif",
        fontSize: 8,
        color: connected ? '#00FF88' : '#FF4444',
        letterSpacing: '0.1em',
      }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: connected ? '#00FF88' : '#FF4444', display: 'inline-block', boxShadow: connected ? '0 0 8px #00FF88' : 'none' }} />
        {connected ? 'LIVE FEED ACTIVE' : error ?? 'CONNECTING...'}
        {connected && (
          <span style={{ marginLeft: 'auto', color: 'rgba(0,207,255,0.5)' }}>
            {detections.length} OBJ DETECTED
          </span>
        )}
      </div>

      {/* Video frame */}
      <div style={{ position: 'relative', lineHeight: 0 }}>
        <img
          ref={imgRef}
          alt="camera"
          style={{ width: '100%', display: 'block', filter: 'brightness(0.9) saturate(0.8) contrast(1.1)' }}
          onLoad={(e) => {
            const img = e.currentTarget
            setImgNaturalSize({ w: img.naturalWidth, h: img.naturalHeight })
          }}
        />

        {/* YOLO detection overlays */}
        <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
          {detections.map((det, i) => {
            const [x, y, w, h] = det.bbox
            const rx = x * scaleX
            const ry = y * scaleY
            const rw = w * scaleX
            const rh = h * scaleY
            return (
              <g key={i}>
                <rect x={rx} y={ry} width={rw} height={rh}
                  fill="none"
                  stroke="#00CFFF"
                  strokeWidth={1.5}
                  opacity={0.85}
                />
                {/* Corner accents */}
                <line x1={rx} y1={ry} x2={rx + 12} y2={ry} stroke="#00CFFF" strokeWidth={2.5} />
                <line x1={rx} y1={ry} x2={rx} y2={ry + 12} stroke="#00CFFF" strokeWidth={2.5} />
                <line x1={rx + rw} y1={ry} x2={rx + rw - 12} y2={ry} stroke="#00CFFF" strokeWidth={2.5} />
                <line x1={rx + rw} y1={ry} x2={rx + rw} y2={ry + 12} stroke="#00CFFF" strokeWidth={2.5} />
                {/* Label */}
                <rect x={rx} y={ry - 18} width={Math.max(rw * 0.7, 80)} height={16}
                  fill="rgba(0,10,20,0.85)"
                  stroke="rgba(0,207,255,0.4)"
                  strokeWidth={0.8}
                />
                <text x={rx + 4} y={ry - 5}
                  fontFamily="Orbitron, sans-serif"
                  fontSize={8}
                  fill="#00CFFF"
                  letterSpacing="1"
                >
                  {det.label.toUpperCase()} {Math.round(det.confidence * 100)}%
                </text>
              </g>
            )
          })}
        </svg>

        {/* Scan grid overlay */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          backgroundImage: `
            linear-gradient(rgba(0,207,255,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,207,255,0.03) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
        }} />
      </div>

      {/* Detection list */}
      {detections.length > 0 && (
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6,
        }}>
          {detections.map((d, i) => (
            <span key={i} style={{
              fontFamily: "'Orbitron', sans-serif",
              fontSize: 7,
              color: '#00CFFF',
              background: 'rgba(0,207,255,0.08)',
              border: '1px solid rgba(0,207,255,0.2)',
              padding: '1px 5px',
              letterSpacing: '0.08em',
            }}>
              {d.label.toUpperCase()}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
