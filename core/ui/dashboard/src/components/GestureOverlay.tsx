import { useEffect, useRef, useState, useCallback } from 'react'
import { useVectorStore } from '../store/vectorStore'

interface GestureData {
  gesture: string
  confidence: number
  fingertip_x: number
  fingertip_y: number
  hand_visible: boolean
}

export default function GestureOverlay() {
  const addContentWindow = useVectorStore((s) => s.addContentWindow)
  const removeContentWindow = useVectorStore((s) => s.removeContentWindow)
  const contentWindows = useVectorStore((s) => s.contentWindows)
  const clearContentWindows = useVectorStore((s) => s.clearContentWindows)
  const scrollToPanel = useVectorStore((s) => s.scrollToPanel)
  const [lastDismissed, setLastDismissed] = useState<typeof contentWindows[0] | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const [dot, setDot] = useState<{ x: number; y: number } | null>(null)
  const [gesture, setGesture] = useState<string>('')
  const [gestureFlash, setGestureFlash] = useState(false)
  const lastGestureRef = useRef<string>('')
  const gestureTimeRef = useRef<number>(0)

  useEffect(() => {
    const tryConnect = () => {
      try {
        const ws = new WebSocket(`ws://${window.location.host}/gesture/ws`)
        wsRef.current = ws

        ws.onmessage = (e) => {
          try {
            const data: GestureData = JSON.parse(e.data)
            if (data.hand_visible) {
              setDot({ x: data.fingertip_x * window.innerWidth, y: data.fingertip_y * window.innerHeight })
            } else {
              setDot(null)
            }

            if (data.gesture && data.confidence > 0.75) {
              const now = Date.now()
              // Debounce: only trigger same gesture after 1.5s
              if (data.gesture !== lastGestureRef.current || now - gestureTimeRef.current > 1500) {
                lastGestureRef.current = data.gesture
                gestureTimeRef.current = now
                handleGesture(data.gesture)
              }
            }
          } catch { /* ignore malformed */ }
        }

        ws.onerror = () => {}
        ws.onclose = () => { setTimeout(tryConnect, 3000) }
      } catch { /* gesture WS not available yet */ }
    }

    tryConnect()
    return () => wsRef.current?.close()
  }, [])

  const handleGesture = (g: string) => {
    setGesture(g)
    setGestureFlash(true)
    setTimeout(() => setGestureFlash(false), 800)

    switch (g) {
      case 'swipe_left':
        if (contentWindows.length > 0) {
          const last = contentWindows[contentWindows.length - 1]
          setLastDismissed(last)
          removeContentWindow(last.id)
        }
        break
      case 'swipe_right':
        if (lastDismissed) {
          addContentWindow({ ...lastDismissed, id: `restored-${Date.now()}` })
          setLastDismissed(null)
        }
        break
      case 'fist':
        clearContentWindows()
        break
      case 'open_palm':
        addContentWindow({
          id: `gesture-${Date.now()}`,
          type: 'text',
          title: 'GESTURE INPUT',
          content: 'Open palm detected. Speak a command or type in the terminal.',
        })
        break
      case 'pinch':
        if (contentWindows.length > 1) {
          contentWindows.slice(1).forEach(w => removeContentWindow(w.id))
        }
        break
      case 'point':
        scrollToPanel('districts')
        break
    }
  }

  if (!dot && !gestureFlash) return null

  return (
    <>
      {/* Tracking dot at fingertip */}
      {dot && (
        <div style={{
          position: 'fixed',
          left: dot.x - 8,
          top: dot.y - 8,
          width: 16,
          height: 16,
          borderRadius: '50%',
          background: '#00CFFF',
          boxShadow: '0 0 20px #00CFFF, 0 0 40px rgba(0,207,255,0.6)',
          zIndex: 999,
          pointerEvents: 'none',
          transition: 'left 0.05s linear, top 0.05s linear',
        }} />
      )}

      {/* Gesture label */}
      {gestureFlash && gesture && (
        <div style={{
          position: 'fixed',
          bottom: 120,
          left: '50%',
          transform: 'translateX(-50%)',
          fontFamily: "'Orbitron', sans-serif",
          fontSize: 14,
          color: '#00CFFF',
          letterSpacing: '0.2em',
          textShadow: '0 0 30px rgba(0,207,255,0.8)',
          zIndex: 998,
          pointerEvents: 'none',
          animation: 'gestureFlashAnim 0.8s ease forwards',
        }}>
          {gesture.toUpperCase().replace('_', ' ')}
        </div>
      )}

      <style>{`
        @keyframes gestureFlashAnim {
          0% { opacity: 0; transform: translateX(-50%) translateY(10px); }
          20% { opacity: 1; transform: translateX(-50%) translateY(0); }
          80% { opacity: 1; }
          100% { opacity: 0; transform: translateX(-50%) translateY(-10px); }
        }
      `}</style>
    </>
  )
}
