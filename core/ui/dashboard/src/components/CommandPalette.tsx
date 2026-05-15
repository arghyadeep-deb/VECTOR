/* ═══════════════════════════════════════════════════════════════════════════
   VECTOR — CommandPalette
   Cmd+K (or Ctrl+K) global launcher.
   Matches VECTOR HUD aesthetic — deep navy + cyan accent.
   ═══════════════════════════════════════════════════════════════════════════ */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Z } from '../lib/zIndex'

type CommandKind = 'agent' | 'district' | 'workflow' | 'system' | 'navigation'

interface Command {
  id: string
  label: string
  hint?: string
  kind: CommandKind
  shortcut?: string
  /** Called when command is selected. */
  run: () => void | Promise<void>
}

const KIND_COLORS: Record<CommandKind, string> = {
  agent: 'var(--cyan)',
  district: 'var(--teal)',
  workflow: 'var(--purple)',
  system: 'var(--amber)',
  navigation: 'var(--cyan-dim)',
}

const KIND_LABELS: Record<CommandKind, string> = {
  agent: 'AGENT',
  district: 'DISTRICT',
  workflow: 'WORKFLOW',
  system: 'SYSTEM',
  navigation: 'NAV',
}

/** Default built-in commands. Districts/agents can be added at runtime via
 *  registerCommand() exposed on window.vectorCmds. */
const DEFAULT_COMMANDS: Command[] = [
  { id: 'reload',     label: 'Reload dashboard',           hint: 'Hot-reload the HUD',          kind: 'system',     shortcut: '⌘R',  run: () => window.location.reload() },
  { id: 'fullscreen', label: 'Toggle fullscreen',          hint: 'Maximize the HUD',            kind: 'system',                    run: () => { const d: any = document; (d.fullscreenElement ? d.exitFullscreen() : d.documentElement.requestFullscreen()) } },
  { id: 'open-logs',  label: 'Open log folder',            hint: '~/.vector/logs/',             kind: 'system',                    run: async () => { try { const { invoke } = await import('@tauri-apps/api/core'); await invoke('open_log_folder') } catch {} } },
  { id: 'doctor',     label: 'Run vector doctor',          hint: 'Comprehensive health check',  kind: 'system',                    run: async () => { try { await fetch('/api/doctor/run', { method: 'POST' }) } catch {} } },
  { id: 'workflow-d', label: 'Trigger morning_digest',     hint: 'DAG workflow',                kind: 'workflow',                  run: async () => { await fetch('/api/workflow/trigger', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'morning_digest' }) }) } },
  { id: 'nav-tel',    label: 'Focus telemetry panel',      hint: 'Switch left column',          kind: 'navigation', shortcut: '⌘1', run: () => document.dispatchEvent(new CustomEvent('vector:focus', { detail: 'telemetry' })) },
  { id: 'nav-dis',    label: 'Focus districts panel',      hint: 'Switch right column',         kind: 'navigation', shortcut: '⌘2', run: () => document.dispatchEvent(new CustomEvent('vector:focus', { detail: 'districts' })) },
  { id: 'nav-cmd',    label: 'Focus command input',        hint: 'Center prompt',               kind: 'navigation', shortcut: '⌘3', run: () => document.dispatchEvent(new CustomEvent('vector:focus', { detail: 'command' })) },
]

/* ── Public registry — districts/agents can register at runtime ─────────── */

const externalCommands: Command[] = []

declare global {
  interface Window {
    vectorCmds?: {
      register: (cmd: Command) => void
      unregister: (id: string) => void
      list: () => Command[]
    }
  }
}

if (typeof window !== 'undefined' && !window.vectorCmds) {
  window.vectorCmds = {
    register: (cmd) => {
      if (!externalCommands.find((c) => c.id === cmd.id)) externalCommands.push(cmd)
    },
    unregister: (id) => {
      const i = externalCommands.findIndex((c) => c.id === id)
      if (i >= 0) externalCommands.splice(i, 1)
    },
    list: () => [...externalCommands],
  }
}

/* ── Component ──────────────────────────────────────────────────────────── */

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // Cmd/Ctrl+K toggle
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIdx(0)
      setTimeout(() => inputRef.current?.focus(), 16)
    }
  }, [open])

  const all = useMemo(() => [...DEFAULT_COMMANDS, ...externalCommands], [open])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return all
    return all.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        (c.hint || '').toLowerCase().includes(q) ||
        c.kind.toLowerCase().includes(q),
    )
  }, [query, all])

  // Reset cursor when filter changes
  useEffect(() => setActiveIdx(0), [query])

  if (!open) return null

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx((i) => Math.min(filtered.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter' && filtered[activeIdx]) {
      e.preventDefault()
      const cmd = filtered[activeIdx]
      setOpen(false)
      void cmd.run()
    }
  }

  return (
    <div
      onClick={() => setOpen(false)}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(2, 8, 16, 0.78)',
        backdropFilter: 'blur(8px)',
        zIndex: Z.MODAL ?? 9999,
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
        paddingTop: '14vh',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(640px, 92vw)',
          background: 'var(--panel-glass)',
          border: '1px solid var(--theme-accent)',
          boxShadow: '0 0 0 1px rgba(0,212,255,0.2), 0 24px 80px -20px rgba(0,212,255,0.35), 0 0 60px -10px rgba(0,212,255,0.4)',
          borderRadius: 4,
          fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          color: '#a8d8f0',
          overflow: 'hidden',
        }}
      >
        {/* Top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 14px',
          borderBottom: '1px solid var(--panel-border)',
          background: 'linear-gradient(180deg, rgba(0,212,255,0.08), transparent)',
        }}>
          <span style={{
            color: 'var(--cyan)',
            fontFamily: "'Orbitron', sans-serif",
            fontWeight: 700, letterSpacing: 2, fontSize: 11,
          }}>VECTOR ⌘K</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search commands, agents, workflows…"
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              color: '#e6f1ff', fontSize: 14, fontFamily: 'inherit',
              caretColor: 'var(--cyan)',
            }}
          />
          <span style={{ color: 'var(--cyan-dim)', fontSize: 10 }}>
            {filtered.length} match{filtered.length === 1 ? '' : 'es'}
          </span>
        </div>

        {/* Results */}
        <div style={{
          maxHeight: '52vh', overflowY: 'auto',
          scrollbarWidth: 'thin',
          scrollbarColor: 'var(--cyan-dim) transparent',
        }}>
          {filtered.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--cyan-dim)', fontSize: 12 }}>
              No commands matched "<span style={{ color: 'var(--cyan)' }}>{query}</span>"
            </div>
          ) : (
            filtered.map((cmd, i) => (
              <div
                key={cmd.id}
                onMouseEnter={() => setActiveIdx(i)}
                onClick={() => { setOpen(false); void cmd.run() }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 14px',
                  borderLeft: i === activeIdx ? '2px solid var(--cyan)' : '2px solid transparent',
                  background: i === activeIdx
                    ? 'linear-gradient(90deg, rgba(0,212,255,0.12), transparent)'
                    : 'transparent',
                  cursor: 'pointer',
                  transition: 'background 80ms',
                }}
              >
                <span style={{
                  fontSize: 9, fontWeight: 700, letterSpacing: 1.5,
                  color: KIND_COLORS[cmd.kind],
                  width: 56,
                  fontFamily: "'Orbitron', sans-serif",
                }}>
                  {KIND_LABELS[cmd.kind]}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: '#e6f1ff', fontSize: 13 }}>{cmd.label}</div>
                  {cmd.hint && (
                    <div style={{ color: 'var(--cyan-dim)', fontSize: 10, marginTop: 2 }}>{cmd.hint}</div>
                  )}
                </div>
                {cmd.shortcut && (
                  <kbd style={{
                    fontSize: 10, color: 'var(--cyan)',
                    border: '1px solid var(--panel-border)',
                    padding: '2px 6px', borderRadius: 3,
                    background: 'rgba(0,212,255,0.04)',
                  }}>
                    {cmd.shortcut}
                  </kbd>
                )}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          padding: '8px 14px',
          borderTop: '1px solid var(--panel-border)',
          fontSize: 10, color: 'var(--cyan-dim)',
        }}>
          <span>↑↓ navigate · ↵ run · esc close</span>
          <span>{externalCommands.length} runtime + {DEFAULT_COMMANDS.length} built-in</span>
        </div>
      </div>
    </div>
  )
}
