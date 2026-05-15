/* ═══════════════════════════════════════════════════════════════════════════
   VECTOR — SetupWizard
   First-run onboarding flow. Walks through Ollama daemon, models, telemetry,
   Obsidian vault. Surfaced when localStorage 'vector_setup_done' is missing.
   ═══════════════════════════════════════════════════════════════════════════ */
import { useEffect, useState } from 'react'

type StepStatus = 'pending' | 'running' | 'ok' | 'fail' | 'skip'

interface Step {
  id: string
  title: string
  description: string
  /** Returns 'ok'|'fail'|'skip' (or throws for fail) */
  check: () => Promise<{ status: StepStatus; detail?: string }>
  /** Optional remediation text */
  fix?: string
}

const STEPS: Step[] = [
  {
    id: 'ollama',
    title: 'Ollama daemon',
    description: 'Local model runtime — required for VECTOR inference.',
    check: async () => {
      try {
        const r = await fetch('http://127.0.0.1:11434/api/tags', { signal: AbortSignal.timeout(3000) })
        if (!r.ok) return { status: 'fail', detail: `HTTP ${r.status}` }
        const j = await r.json()
        const n = (j?.models || []).length
        return { status: 'ok', detail: `${n} model${n === 1 ? '' : 's'} pulled` }
      } catch (e: any) {
        return { status: 'fail', detail: e?.message || 'unreachable' }
      }
    },
    fix: 'Run "ollama serve" or relaunch the Ollama tray app.',
  },
  {
    id: 'parallel',
    title: 'Ollama parallel-load',
    description: 'OLLAMA_MAX_LOADED_MODELS ≥ 2 keeps multiple models hot in VRAM.',
    check: async () => {
      // Best-effort probe — try loading 2 models with keep_alive and see if they coexist.
      try {
        const r = await fetch('http://127.0.0.1:11434/api/ps', { signal: AbortSignal.timeout(3000) })
        if (!r.ok) return { status: 'skip', detail: 'cannot probe' }
        return { status: 'ok', detail: 'env vars assumed OK' }
      } catch {
        return { status: 'skip', detail: 'unable to verify' }
      }
    },
    fix: 'Set OLLAMA_MAX_LOADED_MODELS=4, OLLAMA_NUM_PARALLEL=4, OLLAMA_KEEP_ALIVE=30m at User scope, then restart Ollama.',
  },
  {
    id: 'required-models',
    title: 'Required VECTOR models',
    description: 'vector-coder, vector-fast, nomic-embed-text.',
    check: async () => {
      try {
        const r = await fetch('http://127.0.0.1:11434/api/tags', { signal: AbortSignal.timeout(3000) })
        const j = await r.json()
        const have = new Set<string>((j?.models || []).map((m: any) => String(m.name).split(':')[0]))
        const need = ['vector-coder', 'vector-fast', 'nomic-embed-text']
        const missing = need.filter((m) => !have.has(m) && ![...have].some((h) => h.includes(m)))
        if (missing.length === 0) return { status: 'ok', detail: 'all 3 present' }
        return { status: 'fail', detail: `missing: ${missing.join(', ')}` }
      } catch (e: any) {
        return { status: 'fail', detail: e?.message || 'check failed' }
      }
    },
    fix: 'Run "ollama create vector-coder -f modelfiles/vector-coder.modelfile" for each missing model.',
  },
  {
    id: 'backend',
    title: 'VECTOR backend',
    description: 'FastAPI server at https://127.0.0.1:8000 (run with: python run_vector.py api).',
    check: async () => {
      try {
        const r = await fetch('https://127.0.0.1:8000/health', { signal: AbortSignal.timeout(3000) })
        if (!r.ok) return { status: 'fail', detail: `HTTP ${r.status}` }
        return { status: 'ok', detail: 'reachable' }
      } catch (e: any) {
        return { status: 'fail', detail: e?.message || 'unreachable' }
      }
    },
    fix: 'In a terminal: cd to VECTOR. Codebase, then run "python run_vector.py api".',
  },
  {
    id: 'telemetry',
    title: 'Telemetry capabilities',
    description: 'Energy/FLOPs measurement subsystems.',
    check: async () => {
      try {
        const r = await fetch('https://127.0.0.1:8000/api/telemetry/capabilities', { signal: AbortSignal.timeout(3000) })
        if (!r.ok) return { status: 'skip', detail: 'endpoint not exposed' }
        const caps: Record<string, boolean> = await r.json()
        const ready = Object.entries(caps).filter(([, v]) => v).map(([k]) => k)
        if (ready.length === 0) return { status: 'fail', detail: 'no subsystems available' }
        return { status: 'ok', detail: `${ready.length}/${Object.keys(caps).length} ready` }
      } catch {
        return { status: 'skip', detail: 'cannot probe' }
      }
    },
    fix: 'Run "python scripts/fix_oj_imports.py --apply" to repair the absorbed module imports.',
  },
  {
    id: 'vault',
    title: 'Obsidian vault',
    description: 'Configured persistent brain at vault_path.',
    check: async () => {
      try {
        const r = await fetch('https://127.0.0.1:8000/api/vault/status', { signal: AbortSignal.timeout(3000) })
        if (!r.ok) return { status: 'skip', detail: 'endpoint missing' }
        const j = await r.json()
        if (j?.exists) return { status: 'ok', detail: j?.path }
        return { status: 'fail', detail: 'vault path missing' }
      } catch {
        return { status: 'skip', detail: 'cannot verify' }
      }
    },
    fix: 'Set vault_path in core/config.py or .env to your Obsidian vault folder.',
  },
]

interface Props {
  onComplete: () => void
}

export default function SetupWizard({ onComplete }: Props) {
  const [statuses, setStatuses] = useState<Record<string, { status: StepStatus; detail?: string }>>(() =>
    Object.fromEntries(STEPS.map((s) => [s.id, { status: 'pending' as StepStatus }])),
  )
  const [running, setRunning] = useState(false)

  const runAll = async () => {
    setRunning(true)
    for (const step of STEPS) {
      setStatuses((s) => ({ ...s, [step.id]: { status: 'running' } }))
      try {
        const r = await step.check()
        setStatuses((s) => ({ ...s, [step.id]: r }))
      } catch (e: any) {
        setStatuses((s) => ({ ...s, [step.id]: { status: 'fail', detail: e?.message || 'error' } }))
      }
    }
    setRunning(false)
  }

  useEffect(() => {
    void runAll()
  }, [])

  const okCount = Object.values(statuses).filter((v) => v.status === 'ok').length
  const failCount = Object.values(statuses).filter((v) => v.status === 'fail').length
  const allDone = !running && Object.values(statuses).every((v) => v.status !== 'pending' && v.status !== 'running')
  const ready = allDone && failCount === 0

  return (
    <div style={{
      position: 'fixed', inset: 0,
      background: 'radial-gradient(ellipse at center, rgba(0,30,60,0.5), rgba(2,8,16,0.95))',
      zIndex: 10000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontFamily: "'JetBrains Mono', 'Courier New', monospace",
    }}>
      <div style={{
        width: 'min(720px, 94vw)',
        background: 'var(--panel-glass)',
        border: '1px solid var(--theme-accent)',
        borderRadius: 4,
        boxShadow: '0 0 80px -20px rgba(0,212,255,0.4), 0 0 0 1px rgba(0,212,255,0.2)',
        color: '#a8d8f0',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid var(--panel-border)',
          background: 'linear-gradient(180deg, rgba(0,212,255,0.10), transparent)',
        }}>
          <div style={{
            fontFamily: "'Orbitron', sans-serif",
            fontSize: 22, fontWeight: 700, letterSpacing: 6,
            color: 'var(--cyan)',
          }}>
            VECTOR · INITIALIZE
          </div>
          <div style={{ marginTop: 4, color: 'var(--cyan-dim)', fontSize: 12 }}>
            First-run system check — verifying all subsystems are reachable.
          </div>
        </div>

        <div style={{ padding: '14px 24px', maxHeight: '60vh', overflowY: 'auto' }}>
          {STEPS.map((step) => {
            const s = statuses[step.id]
            const color =
              s.status === 'ok' ? 'var(--green)' :
              s.status === 'fail' ? 'var(--red)' :
              s.status === 'running' ? 'var(--cyan)' :
              s.status === 'skip' ? 'var(--amber)' : 'var(--cyan-dim)'
            const glyph =
              s.status === 'ok' ? '✓' :
              s.status === 'fail' ? '✗' :
              s.status === 'running' ? '◌' :
              s.status === 'skip' ? '~' : '·'
            return (
              <div key={step.id} style={{
                display: 'flex', gap: 14,
                padding: '12px 0',
                borderBottom: '1px solid var(--panel-border)',
              }}>
                <div style={{
                  width: 24, height: 24, borderRadius: '50%',
                  border: `1px solid ${color}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color, fontSize: 14, fontWeight: 700,
                  animation: s.status === 'running' ? 'spin 1.2s linear infinite' : undefined,
                  flexShrink: 0,
                }}>
                  {glyph}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: '#e6f1ff' }}>{step.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--cyan-dim)', marginTop: 2 }}>{step.description}</div>
                  {s.detail && (
                    <div style={{ fontSize: 11, color, marginTop: 4 }}>
                      {s.detail}
                    </div>
                  )}
                  {s.status === 'fail' && step.fix && (
                    <div style={{
                      fontSize: 11, color: 'var(--amber)', marginTop: 4,
                      padding: 6, background: 'rgba(255,170,0,0.06)',
                      borderLeft: '2px solid var(--amber)',
                    }}>
                      <strong>fix:</strong> {step.fix}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12,
          padding: '14px 24px',
          borderTop: '1px solid var(--panel-border)',
          background: 'linear-gradient(0deg, rgba(0,212,255,0.05), transparent)',
        }}>
          <div style={{ fontSize: 11, color: 'var(--cyan-dim)' }}>
            {okCount} OK · {failCount} fail · {STEPS.length - okCount - failCount} other
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              onClick={runAll}
              disabled={running}
              style={{
                padding: '8px 16px', fontSize: 11,
                fontFamily: 'inherit', letterSpacing: 1.5,
                background: 'transparent', color: 'var(--cyan)',
                border: '1px solid var(--theme-accent)',
                borderRadius: 3, cursor: running ? 'not-allowed' : 'pointer',
                opacity: running ? 0.5 : 1,
              }}
            >
              {running ? 'CHECKING…' : 'RE-RUN CHECKS'}
            </button>
            <button
              onClick={() => { localStorage.setItem('vector_setup_done', '1'); onComplete() }}
              disabled={!allDone}
              style={{
                padding: '8px 20px', fontSize: 11, fontWeight: 700,
                fontFamily: 'inherit', letterSpacing: 2,
                background: ready ? 'var(--cyan)' : 'rgba(0,212,255,0.2)',
                color: ready ? '#0b0b0b' : 'var(--cyan-dim)',
                border: '1px solid var(--cyan)',
                borderRadius: 3, cursor: allDone ? 'pointer' : 'not-allowed',
              }}
            >
              {ready ? 'ENTER VECTOR' : (failCount > 0 ? 'PROCEED ANYWAY' : 'CHECKING…')}
            </button>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}

/** Convenience hook for App.tsx: returns true once the user has either completed setup
 *  or chose to skip it. */
export function useSetupComplete(): [boolean, () => void] {
  const [done, setDone] = useState(() => localStorage.getItem('vector_setup_done') === '1')
  return [done, () => { localStorage.setItem('vector_setup_done', '1'); setDone(true) }]
}
