import { useRef, useCallback, useEffect, useState } from 'react'

export interface CameraState {
  x: number
  y: number
  zoom: number
}

const LERP = 0.08

export function useCamera(initialZoom = 1) {
  const [camera, setCamera] = useState<CameraState>({ x: 0, y: 0, zoom: initialZoom })
  const target = useRef({ x: 0, y: 0, zoom: initialZoom })
  const raf = useRef<number>(0)
  const animating = useRef(false)

  const tick = useCallback(() => {
    setCamera((prev) => {
      const t = target.current
      const nx = prev.x + (t.x - prev.x) * LERP
      const ny = prev.y + (t.y - prev.y) * LERP
      const nz = prev.zoom + (t.zoom - prev.zoom) * LERP

      if (
        Math.abs(nx - t.x) < 0.05 &&
        Math.abs(ny - t.y) < 0.05 &&
        Math.abs(nz - t.zoom) < 0.001
      ) {
        animating.current = false
        return { x: t.x, y: t.y, zoom: t.zoom }
      }

      animating.current = true
      return { x: nx, y: ny, zoom: nz }
    })

    if (animating.current) {
      raf.current = requestAnimationFrame(tick)
    }
  }, [])

  useEffect(() => {
    return () => cancelAnimationFrame(raf.current)
  }, [])

  const pan = useCallback((dx: number, dy: number) => {
    setCamera((prev) => {
      const nx = prev.x - dx / prev.zoom
      const ny = prev.y - dy / prev.zoom
      target.current = { x: nx, y: ny, zoom: prev.zoom }
      return { x: nx, y: ny, zoom: prev.zoom }
    })
  }, [])

  const zoomAt = useCallback((clientX: number, clientY: number, factor: number) => {
    setCamera((prev) => {
      const vw = window.innerWidth
      const vh = window.innerHeight
      const worldX = (clientX - vw / 2) / prev.zoom + prev.x
      const worldY = (clientY - vh / 2) / prev.zoom + prev.y
      const nz = Math.max(0.25, Math.min(10, prev.zoom * factor))
      const nx = worldX - (clientX - vw / 2) / nz
      const ny = worldY - (clientY - vh / 2) / nz
      target.current = { x: nx, y: ny, zoom: nz }
      animating.current = true
      raf.current = requestAnimationFrame(tick)
      return prev
    })
  }, [tick])

  const focusOn = useCallback((worldX: number, worldY: number, zoom = 2) => {
    target.current = { x: worldX, y: worldY, zoom }
    animating.current = true
    raf.current = requestAnimationFrame(tick)
  }, [tick])

  const reset = useCallback(() => {
    target.current = { x: 0, y: 0, zoom: initialZoom }
    animating.current = true
    raf.current = requestAnimationFrame(tick)
  }, [initialZoom, tick])

  return { camera, pan, zoomAt, focusOn, reset }
}
