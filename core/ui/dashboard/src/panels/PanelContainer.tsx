import { useState, useRef, useCallback, type ReactNode } from 'react'

interface Props {
  id: string
  title: string
  defaultPos?: { x: number; y: number }
  defaultSize?: { w: number; h: number }
  children: ReactNode
  onClose?: (id: string) => void
}

export default function PanelContainer({ id, title, defaultPos, defaultSize, children, onClose }: Props) {
  const [pos, setPos] = useState(defaultPos || { x: 100, y: 100 })
  const [size] = useState(defaultSize || { w: 320, h: 400 })
  const [collapsed, setCollapsed] = useState(false)
  const [dragging, setDragging] = useState(false)
  const dragRef = useRef({ startX: 0, startY: 0, origX: 0, origY: 0 })

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setDragging(true)
    dragRef.current.startX = e.clientX
    dragRef.current.startY = e.clientY
    dragRef.current.origX = pos.x
    dragRef.current.origY = pos.y
  }, [pos])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return
    const dx = e.clientX - dragRef.current.startX
    const dy = e.clientY - dragRef.current.startY
    setPos({
      x: dragRef.current.origX + dx,
      y: dragRef.current.origY + dy,
    })
  }, [dragging])

  const handleMouseUp = useCallback(() => {
    setDragging(false)
  }, [])

  const CYAN = '#00CFFF'

  return (
    <div
      style={{
        position: 'fixed',
        left: pos.x,
        top: pos.y,
        width: collapsed ? 280 : size.w,
        zIndex: 1000,
        fontFamily: "'JetBrains Mono', monospace",
        pointerEvents: 'auto',
        userSelect: dragging ? 'none' : 'auto',
      }}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
    >
      <div
        onMouseDown={handleMouseDown}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 10px',
          background: 'rgba(5, 13, 26, 0.92)',
          border: `1px solid rgba(0,212,255,0.15)`,
          cursor: 'grab',
          fontSize: 10,
          color: CYAN,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
        }}
      >
        <span>{title}</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={(e) => { e.stopPropagation(); setCollapsed((c) => !c) }}
            style={{ background: 'none', border: '1px solid rgba(0,212,255,0.2)', color: CYAN, fontSize: 10, cursor: 'pointer', padding: '1px 6px' }}
          >
            {collapsed ? '▸' : '▾'}
          </button>
          {onClose && (
            <button
              onClick={(e) => { e.stopPropagation(); onClose(id) }}
              style={{ background: 'none', border: '1px solid rgba(0,212,255,0.2)', color: '#FF4444', fontSize: 10, cursor: 'pointer', padding: '1px 6px' }}
            >
              ✕
            </button>
          )}
        </div>
      </div>
      {!collapsed && (
        <div
          style={{
            background: 'rgba(5, 13, 26, 0.88)',
            border: '1px solid rgba(0,212,255,0.08)',
            borderTop: 'none',
            boxShadow: '0 0 20px rgba(0,212,255,0.06), inset 0 0 30px rgba(0,212,255,0.02)',
            maxHeight: size.h,
            overflow: 'auto',
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}
