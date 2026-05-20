import { useRef, useCallback, useEffect, type ReactNode } from 'react'
import { useCamera } from '../hooks/useCamera'
import { useVectorStore } from '../store/vectorStore'
import DetailPane from './DetailPane'

export interface PanelPlacement {
  id: string
  worldX: number
  worldY: number
  component: ReactNode
  title?: string
  fixed?: boolean
}

interface Props {
  children?: ReactNode
  panels: PanelPlacement[]
  focusedPanel: string | null
  onFocusPanel: (id: string | null) => void
  cameraRef?: { current: { focusOn: (x: number, y: number, zoom?: number) => void; reset: () => void } | null }
}

export default function InfiniteCanvas({ children, panels, focusedPanel, onFocusPanel, cameraRef }: Props) {
  const { camera, pan, zoomAt, focusOn, reset } = useCamera(1)
  const isDragging = useRef(false)
  const lastPos = useRef({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)
  const scrollTarget = useVectorStore((s) => s.scrollTarget)
  const clearScrollTarget = useVectorStore((s) => s.clearScrollTarget)

  useEffect(() => {
    if (scrollTarget) {
      focusOn(scrollTarget.worldX, scrollTarget.worldY, scrollTarget.zoom ?? 2.5)
      clearScrollTarget()
    }
  }, [scrollTarget, focusOn, clearScrollTarget])

  useEffect(() => {
    if (cameraRef) cameraRef.current = { focusOn, reset }
  }, [focusOn, reset, cameraRef])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement
    if (target.closest('[data-panel]') || target.closest('[data-detail]')) return
    isDragging.current = true
    lastPos.current = { x: e.clientX, y: e.clientY }
    if (containerRef.current) containerRef.current.style.cursor = 'grabbing'
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging.current) return
    pan(e.clientX - lastPos.current.x, e.clientY - lastPos.current.y)
    lastPos.current = { x: e.clientX, y: e.clientY }
  }, [pan])

  const handleMouseUp = useCallback(() => {
    isDragging.current = false
    if (containerRef.current) containerRef.current.style.cursor = 'grab'
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const handler = (e: WheelEvent) => {
      e.preventDefault()
      if (e.ctrlKey || e.metaKey) {
        zoomAt(e.clientX, e.clientY, e.deltaY > 0 ? 0.92 : 1.08)
      } else {
        pan(-e.deltaX, -e.deltaY)
      }
    }
    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, [zoomAt, pan])

  const handlePanelClick = useCallback((id: string) => {
    if (isDragging.current) return
    const p = panels.find((pl) => pl.id === id)
    if (p) {
      if (!p.fixed) {
        focusOn(p.worldX, p.worldY, 2.5)
      }
      onFocusPanel(id)
    }
  }, [panels, focusOn, onFocusPanel])

  const handleDetailClose = useCallback(() => {
    reset()
    onFocusPanel(null)
  }, [reset, onFocusPanel])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && focusedPanel) {
      handleDetailClose()
    }
  }, [focusedPanel, handleDetailClose])

  const vw = typeof window !== 'undefined' ? window.innerWidth : 1920
  const vh = typeof window !== 'undefined' ? window.innerHeight : 1080
  const tx = vw / 2 - camera.x * camera.zoom
  const ty = vh / 2 - camera.y * camera.zoom

  const focusedDef = focusedPanel ? panels.find((p) => p.id === focusedPanel) : null

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onKeyDown={handleKeyDown}
      style={{
        position: 'fixed', inset: 0, zIndex: 5, overflow: 'hidden',
        cursor: 'grab', userSelect: 'none', outline: 'none',
      }}
    >
      <style>{`
        [data-panel]:hover {
          filter: brightness(1.25) !important;
          opacity: 1 !important;
          z-index: 10;
          box-shadow: 0 0 0 1.5px rgba(0,212,255,0.7), 0 0 16px rgba(0,212,255,0.4), 0 0 32px rgba(0,212,255,0.12) !important;
        }
        [data-panel]:hover * {
          text-shadow: 0 0 8px rgba(0,212,255,0.4), 0 0 20px rgba(0,212,255,0.15) !important;
        }
      `}</style>
      <div
        style={{
          transform: `translate(${tx}px, ${ty}px) scale(${camera.zoom})`,
          transformOrigin: '0 0',
          willChange: 'transform',
        }}
      >
        {children}

        {panels.filter((p) => !p.fixed).map((p) => (
          <div
            key={p.id}
            data-panel={p.id}
            onClick={() => handlePanelClick(p.id)}
            style={{
              position: 'absolute',
              left: p.worldX, top: p.worldY,
              width: 180,
              cursor: 'pointer',
              transition: 'filter 0.3s, opacity 0.3s',
              filter: focusedPanel && focusedPanel !== p.id ? 'brightness(0.5) blur(1px)' : 'none',
              opacity: focusedPanel && focusedPanel !== p.id ? 0.4 : 1,
              pointerEvents: focusedPanel && focusedPanel !== p.id ? 'none' : 'auto',
            }}
          >
            {p.component}
          </div>
        ))}

        {focusedDef && !focusedDef.fixed && (
          <div
            data-detail="true"
            style={{
              position: 'absolute',
              left: focusedDef.worldX,
              top: focusedDef.worldY,
              transform: 'translate(-50%, -50%)',
            }}
          >
            <DetailPane panel={focusedDef} onClose={handleDetailClose} />
          </div>
        )}
      </div>
      {focusedDef?.fixed && (
        <div
          data-detail="true"
          style={{
            position: 'fixed',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 200,
          }}
        >
          <DetailPane panel={focusedDef} onClose={handleDetailClose} />
        </div>
      )}
    </div>
  )
}
