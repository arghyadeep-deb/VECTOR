import { startTransition } from 'react'

type TokenCallback = (text: string) => void
type DoneCallback = (full: string) => void
type ErrorCallback = (err: string) => void

let ws: WebSocket | null = null
let onToken: TokenCallback[] = []
let onDone: DoneCallback[] = []
let onError: ErrorCallback[] = []
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let retries = 0
const MAX_RETRIES = 3

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}/ui/ws/chat`
  try {
    ws = new WebSocket(url)
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'token') onToken.forEach((cb) => startTransition(() => cb(msg.text)))
        else if (msg.type === 'done') onDone.forEach((cb) => startTransition(() => cb(msg.full || '')))
        else if (msg.type === 'error') onError.forEach((cb) => startTransition(() => cb(msg.message)))
      } catch { /* ignore parse errors */ }
    }
    ws.onclose = () => {
      ws = null
      if (retries < MAX_RETRIES) {
        const delay = [3000, 5000, 10000][retries] || 10000
        retries++
        reconnectTimer = setTimeout(connect, delay)
      }
    }
    ws.onerror = () => { /* onclose will fire */ }
    retries = 0
  } catch { /* ignore connection errors */ }
}

export function sendMessage(text: string) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false
  ws.send(JSON.stringify({ message: text, history: [] }))
  return true
}

export function onTokenReceived(cb: TokenCallback) { onToken.push(cb); return () => { onToken = onToken.filter((f) => f !== cb) } }
export function onDoneReceived(cb: DoneCallback) { onDone.push(cb); return () => { onDone = onDone.filter((f) => f !== cb) } }
export function onErrorReceived(cb: ErrorCallback) { onError.push(cb); return () => { onError = onError.filter((f) => f !== cb) } }

export function closeWS() {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (ws) { ws.close(); ws = null }
  retries = MAX_RETRIES
}

connect()
