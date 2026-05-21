/**
 * useVectorWS — single source of truth for the dashboard's /ws subscription.
 *
 * Connects to ws://<host>/ws and dispatches three message types into the store:
 *   - {type:"orb_state", state:"listening"|"processing"|"speaking"|"idle"}
 *       → setVoiceState(state)  (drives the orb FSM and the VectorFrame glow)
 *   - {type:"ui_event", action_type, params}
 *       → opens/closes widgets, flies the map, etc. (multi-intent voice → UI)
 *   - any other JSON message is ignored (other panels poll directly)
 *
 * Auto-reconnects with exponential backoff. Never throws.
 */
import { useEffect } from 'react'
import { useVectorStore } from '../store/vectorStore'

let ws: WebSocket | null = null
let reconnectAt: number | null = null
let attempt = 0

function connect(onMsg: (m: unknown) => void): void {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${proto}//${window.location.host}/ws`
  try {
    ws = new WebSocket(url)
  } catch {
    return scheduleReconnect(onMsg)
  }
  ws.onopen = () => { attempt = 0 }
  ws.onmessage = (e) => {
    try { onMsg(JSON.parse(e.data)) } catch { /* non-JSON, ignore */ }
  }
  ws.onerror = () => { /* close handler will fire */ }
  ws.onclose = () => { ws = null; scheduleReconnect(onMsg) }
}

function scheduleReconnect(onMsg: (m: unknown) => void) {
  const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5))
  attempt += 1
  if (reconnectAt) window.clearTimeout(reconnectAt)
  reconnectAt = window.setTimeout(() => connect(onMsg), delay)
}

/**
 * Hook that wires /ws into the store. Call once near the App root.
 */
export function useVectorWS(): void {
  const setVoiceState = useVectorStore((s) => s.setVoiceState)
  const setMode = useVectorStore((s) => s.setMode)
  const addContentWindow = useVectorStore((s) => s.addContentWindow)
  const removeContentWindow = useVectorStore((s) => s.removeContentWindow)
  const clearContentWindows = useVectorStore((s) => s.clearContentWindows)
  const setConnected = useVectorStore((s) => s.setConnected)

  useEffect(() => {
    // Use a ref so the onMsg closure always sees the latest contentWindows
    // without needing to reconnect the WebSocket on every render.
    const storeRef = {
      setVoiceState, setMode, addContentWindow, removeContentWindow,
      clearContentWindows, setConnected,
      get contentWindows() { return useVectorStore.getState().contentWindows },
    }

    const onMsg = (raw: unknown) => {
      if (!raw || typeof raw !== 'object') return
      const m = raw as Record<string, unknown>
      switch (m.type) {
        case 'orb_state': {
          const next = m.state as 'listening' | 'processing' | 'speaking' | 'idle'
          if (['listening', 'processing', 'speaking', 'idle'].includes(next)) {
            storeRef.setVoiceState(next)
          }
          return
        }
        case 'ui_event': {
          const action = m.action_type as string
          const params = (m.params || {}) as Record<string, unknown>
          handleUIEvent(action, params, {
            addContentWindow: storeRef.addContentWindow,
            removeContentWindow: storeRef.removeContentWindow,
            clearContentWindows: storeRef.clearContentWindows,
            contentWindows: storeRef.contentWindows,
            setMode: storeRef.setMode,
          })
          return
        }
        case 'status': {
          storeRef.setConnected(true)
          return
        }
        default:
          return
      }
    }
    connect(onMsg)
    return () => { /* keep open across remounts */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

interface UIEventCtx {
  addContentWindow: (w: { id: string; type: 'text' | 'camera' | 'map' | 'chart'; title: string; content?: string }) => void
  removeContentWindow: (id: string) => void
  clearContentWindows: () => void
  contentWindows: ReadonlyArray<{ id: string; type: string; title: string }>
  setMode: (m: 'ORB_MODE' | 'DASHBOARD_MODE' | 'FORTRESS_MODE') => void
}

const WIDGET_ID_TO_TYPE: Record<string, 'text' | 'camera' | 'map' | 'chart'> = {
  map: 'map', camera: 'camera', news: 'text', schematic: 'text',
  music: 'text', chat: 'text', stock: 'chart', building: 'text',
}

function handleUIEvent(action: string, params: Record<string, unknown>, ctx: UIEventCtx) {
  switch (action) {
    case 'widget_open': {
      const id = String(params.id || '')
      if (!id) return
      const exists = ctx.contentWindows.some((w) => w.id === id)
      if (exists) return
      ctx.addContentWindow({
        id,
        type: WIDGET_ID_TO_TYPE[id] || 'text',
        title: id.charAt(0).toUpperCase() + id.slice(1),
      })
      return
    }
    case 'widget_close': {
      const id = String(params.id || '')
      if (id === 'all') return ctx.clearContentWindows()
      if (id) ctx.removeContentWindow(id)
      return
    }
    case 'widget_show_location': {
      const query = String(params.query || '')
      // Open map widget if not already open, then dispatch a CustomEvent the
      // MapWidget listens for to perform map.flyTo(). Decouples the store
      // from MapLibre internals.
      const exists = ctx.contentWindows.some((w) => w.type === 'map')
      if (!exists) {
        ctx.addContentWindow({ id: 'map', type: 'map', title: query || 'Map' })
      }
      window.dispatchEvent(new CustomEvent('vector:show-location', { detail: { query } }))
      return
    }
    case 'music_play':
    case 'music_pause':
    case 'music_next':
    case 'music_prev': {
      window.dispatchEvent(new CustomEvent('vector:music', { detail: { action } }))
      return
    }
    default:
      return
  }
}
