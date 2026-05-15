import { useState, useEffect } from 'react'

interface OllamaModel {
  name: string
  size_gb: number
  loaded: boolean
}

const MOCK_MODELS: OllamaModel[] = [
  { name: 'vector-focus', size_gb: 3.8, loaded: true },
  { name: 'vector-coder', size_gb: 8.1, loaded: false },
  { name: 'vector-reasoning', size_gb: 8.1, loaded: false },
  { name: 'devstral:24b', size_gb: 13.4, loaded: false },
  { name: 'deepseek-r1:14b', size_gb: 8.5, loaded: false },
  { name: 'qwen3:30b-a3b', size_gb: 17.0, loaded: false },
]

export default function ModelSwitcher() {
  const [models, setModels] = useState<OllamaModel[]>(MOCK_MODELS)
  const [current, setCurrent] = useState<string>('vector-focus')
  const [selected, setSelected] = useState<string>('vector-focus')
  const [switching, setSwitching] = useState(false)
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<'ok' | 'mock'>('mock')

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch('/api/models', { cache: 'no-store' })
        if (!r.ok) throw new Error()
        const d = await r.json()
        setModels(d.models ?? MOCK_MODELS)
        setCurrent(d.current ?? 'vector-focus')
        setSelected(d.current ?? 'vector-focus')
        setStatus('ok')
      } catch {
        setStatus('mock')
      }
    }
    load()
  }, [])

  const switchModel = async () => {
    if (selected === current || switching) return
    setSwitching(true)
    try {
      const r = await fetch('/api/model/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: selected }),
      })
      if (r.ok) {
        setCurrent(selected)
        setModels(ms => ms.map(m => ({ ...m, loaded: m.name === selected })))
      }
    } catch { /* use mock */ }
    setSwitching(false)
    setOpen(false)
  }

  const activeModel = models.find(m => m.name === current) ?? models[0]
  const selModel = models.find(m => m.name === selected) ?? models[0]

  return (
    <div style={{
      background: 'rgba(0,8,20,0.88)',
      border: '1px solid rgba(79,195,247,0.25)',
      borderRadius: 6,
      padding: '8px 10px',
      fontFamily: 'monospace',
      fontSize: 11,
      color: '#B0BEC5',
      position: 'relative',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ color: '#4FC3F7', fontWeight: 700, fontSize: 10, letterSpacing: 1.5 }}>MODEL</span>
        <span style={{ color: status === 'mock' ? '#37474F' : '#4CAF50', fontSize: 9 }}>
          {status === 'mock' ? 'LOCAL' : 'LIVE'}
        </span>
      </div>

      {/* Current model */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
        padding: '4px 6px', background: 'rgba(79,195,247,0.06)', borderRadius: 4,
        border: '1px solid rgba(79,195,247,0.15)',
      }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#4FC3F7', display: 'inline-block', flexShrink: 0 }} />
        <span style={{ color: '#E0F7FA', fontSize: 10, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {current}
        </span>
        <span style={{ color: '#546E7A', fontSize: 9 }}>{activeModel?.size_gb ?? '?'}GB</span>
      </div>

      {/* Dropdown toggle */}
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', padding: '3px 6px', background: 'rgba(255,255,255,0.04)',
          border: '1px solid rgba(79,195,247,0.2)', borderRadius: 4, cursor: 'pointer',
          color: '#78909C', fontSize: 9, textAlign: 'left', display: 'flex', justifyContent: 'space-between',
          fontFamily: 'monospace',
        }}
      >
        <span>{open ? 'collapse ▲' : 'switch model ▼'}</span>
      </button>

      {open && (
        <div style={{
          marginTop: 4, maxHeight: 120, overflowY: 'auto',
          border: '1px solid rgba(79,195,247,0.15)', borderRadius: 4,
          background: 'rgba(0,4,12,0.95)',
        }}>
          {models.map(m => (
            <div
              key={m.name}
              onClick={() => setSelected(m.name)}
              style={{
                padding: '4px 8px', cursor: 'pointer',
                background: selected === m.name ? 'rgba(79,195,247,0.12)' : 'transparent',
                display: 'flex', alignItems: 'center', gap: 6,
              }}
            >
              <span style={{
                width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                background: m.loaded ? '#4FC3F7' : '#37474F',
              }} />
              <span style={{ color: selected === m.name ? '#E0F7FA' : '#78909C', fontSize: 9, flex: 1 }}>{m.name}</span>
              <span style={{ color: '#37474F', fontSize: 8 }}>{m.size_gb}GB</span>
            </div>
          ))}
        </div>
      )}

      {selected !== current && (
        <div style={{ marginTop: 5, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: '#FFB300', fontSize: 9 }}>{selModel?.size_gb ?? '?'}GB VRAM</span>
          <button
            onClick={switchModel}
            disabled={switching}
            style={{
              padding: '2px 8px', background: switching ? 'rgba(79,195,247,0.1)' : 'rgba(79,195,247,0.2)',
              border: '1px solid rgba(79,195,247,0.4)', borderRadius: 3, cursor: switching ? 'not-allowed' : 'pointer',
              color: '#4FC3F7', fontSize: 9, fontFamily: 'monospace',
            }}
          >
            {switching ? 'loading…' : 'SWITCH'}
          </button>
        </div>
      )}
    </div>
  )
}
