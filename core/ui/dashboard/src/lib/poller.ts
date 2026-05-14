import { useState, useEffect, useRef, useCallback, startTransition } from 'react'

type HealthState = 'ok' | 'retrying' | 'dead'

interface PollConfig<T> {
  key: string
  fetcher: () => Promise<T>
  intervalMs: number
  onSuccess?: (data: T) => void
  onError?: (error: string) => void
  onRecovered?: () => void
  maxRetries?: number
}

const health: Record<string, { state: HealthState; retries: number }> = {}

export function usePoll<T>(config: PollConfig<T>) {
  const { key, fetcher, intervalMs, onSuccess, onError, onRecovered, maxRetries = 3 } = config
  const [healthState, setHealthState] = useState<HealthState>(health[key]?.state ?? 'ok')
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    if (!health[key]) health[key] = { state: 'ok', retries: 0 }

    const poll = async () => {
      try {
        const data = await fetcher()
        if (!mountedRef.current) return
        const prev = health[key]
        if (prev.state === 'retrying' || prev.state === 'dead') {
          health[key] = { state: 'ok', retries: 0 }
          setHealthState('ok')
          onRecovered?.()
        }
        startTransition(() => {
          onSuccess?.(data)
        })
      } catch (e: any) {
        if (!mountedRef.current) return
        const entry = health[key]
        entry.retries++
        const msg = e?.message ?? String(e)
        if (entry.retries >= maxRetries) {
          health[key] = { ...entry, state: 'dead' }
          setHealthState('dead')
          onError?.(msg)
        } else {
          health[key] = { ...entry, state: 'retrying' }
          setHealthState('retrying')
          const delay = Math.min(2000 * Math.pow(2, entry.retries - 1), 8000)
          setTimeout(() => { if (mountedRef.current) poll() }, delay)
        }
      }
    }

    poll()
    const id = setInterval(poll, intervalMs)
    return () => { mountedRef.current = false; clearInterval(id) }
  }, [key])

  return healthState
}
