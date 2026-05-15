/* ═══════════════════════════════════════════════════════════════════════════
   VECTOR — useAgentEvents
   SSE subscription to live district / agent events.

   Server-side endpoint convention:
     GET  /api/agents/events         (Server-Sent Events stream)

   Each event has the shape:
     { id, ts, district, agent, kind, payload }

   Where `kind` is one of:
     'started' | 'thinking' | 'tool_call' | 'tool_result'
     | 'completed' | 'failed' | 'speaking' | 'idle'
   ═══════════════════════════════════════════════════════════════════════════ */
import { useEffect, useRef, useState } from 'react'

export interface AgentEvent {
  id: string
  ts: string                 // ISO timestamp
  district: string
  agent: string
  kind:
    | 'started' | 'thinking' | 'tool_call' | 'tool_result'
    | 'completed' | 'failed' | 'speaking' | 'idle' | 'log'
  payload?: any
}

interface Options {
  url?: string
  /** Maximum events to retain in memory. Default 200. */
  maxBuffer?: number
  /** Auto-reconnect with exponential backoff. Default true. */
  autoReconnect?: boolean
  /** Filter — only events whose district matches one of these will be emitted */
  districts?: string[]
  /** Filter — only events whose kind matches one of these */
  kinds?: AgentEvent['kind'][]
}

interface State {
  events: AgentEvent[]
  connected: boolean
  /** Last connection error, if any */
  error?: string
  /** Latest event of each kind for quick access */
  latestByKind: Partial<Record<AgentEvent['kind'], AgentEvent>>
  /** Latest event per district */
  latestByDistrict: Record<string, AgentEvent>
}

const DEFAULT_URL = 'https://127.0.0.1:8000/api/agents/events'

export function useAgentEvents(opts: Options = {}): State {
  const url = opts.url ?? DEFAULT_URL
  const max = opts.maxBuffer ?? 200
  const autoReconnect = opts.autoReconnect ?? true

  const [state, setState] = useState<State>({
    events: [],
    connected: false,
    latestByKind: {},
    latestByDistrict: {},
  })

  const esRef = useRef<EventSource | null>(null)
  const retryRef = useRef(0)
  const teardownRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    let cancelled = false

    const connect = () => {
      if (cancelled) return
      try {
        const es = new EventSource(url, { withCredentials: false })
        esRef.current = es

        es.onopen = () => {
          if (cancelled) return
          retryRef.current = 0
          setState((s) => ({ ...s, connected: true, error: undefined }))
        }

        es.onmessage = (ev: MessageEvent<string>) => {
          if (cancelled) return
          try {
            const parsed = JSON.parse(ev.data) as AgentEvent
            if (!parsed || typeof parsed !== 'object') return
            // Apply filters
            if (opts.districts && !opts.districts.includes(parsed.district)) return
            if (opts.kinds && !opts.kinds.includes(parsed.kind)) return

            setState((s) => {
              const buf = [...s.events, parsed]
              if (buf.length > max) buf.splice(0, buf.length - max)
              return {
                ...s,
                events: buf,
                latestByKind: { ...s.latestByKind, [parsed.kind]: parsed },
                latestByDistrict: { ...s.latestByDistrict, [parsed.district]: parsed },
              }
            })
          } catch {
            /* ignore malformed */
          }
        }

        es.onerror = () => {
          if (cancelled) return
          setState((s) => ({ ...s, connected: false, error: 'connection lost' }))
          es.close()
          esRef.current = null
          if (autoReconnect && !cancelled) {
            retryRef.current += 1
            const delay = Math.min(30_000, 800 * 2 ** retryRef.current)
            setTimeout(connect, delay)
          }
        }
      } catch (e: any) {
        setState((s) => ({ ...s, connected: false, error: e?.message || 'init failed' }))
      }
    }

    connect()
    teardownRef.current = () => {
      cancelled = true
      esRef.current?.close()
      esRef.current = null
    }
    return teardownRef.current
  }, [url, max, autoReconnect, JSON.stringify(opts.districts), JSON.stringify(opts.kinds)])

  return state
}

/** Convenience selector — return only events for a single district. */
export function useDistrictEvents(district: string, opts: Options = {}): AgentEvent[] {
  const { events } = useAgentEvents({ ...opts, districts: [district] })
  return events
}

/** Convenience selector — return current activity status of all known districts. */
export function useDistrictActivity(): Record<string, AgentEvent['kind']> {
  const { latestByDistrict } = useAgentEvents()
  const out: Record<string, AgentEvent['kind']> = {}
  for (const [d, ev] of Object.entries(latestByDistrict)) out[d] = ev.kind
  return out
}
