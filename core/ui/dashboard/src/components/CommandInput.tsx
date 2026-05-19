import { useState, useEffect, useRef, useCallback } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { api } from '../lib/api'
import { sendMessage, onTokenReceived, onDoneReceived, onErrorReceived } from '../lib/websocket'
import VoiceInput from './VoiceInput'

const PANEL_ALIASES: Record<string, string[]> = {
  telemetry: ['telemetry', 'tele', 'system info', 'system information'],
  systemMetrics: ['metrics', 'system metrics', 'performance', 'system monitor'],
  events: ['events', 'event feed', 'activity', 'recent events', 'log'],
  compass: ['compass', 'direction', 'heading', 'navigation'],
  modelSwitcher: ['model', 'models', 'model switcher', 'ai model'],
  coreStatus: ['core', 'core status', 'system status', 'vitals'],
  dailyInfo: ['daily', 'weather', 'briefing', 'daily briefing', 'forecast'],
  vectorCode: ['vectorcode', 'vector code', 'vc', 'code'],
  districts: ['districts', 'agents', 'district', 'agent list'],
  security: ['security', 'threats', 'threat', 'scans', 'threat level'],
  goals: ['goals', 'actions', 'action', 'objectives', 'tasks'],
  council: ['council', 'council sessions', 'deliberation'],
  tasks: ['task queue', 'task status', 'jobs', 'job queue'],
  memory: ['memory', 'memory stats', 'episodes', 'models'],
  command: ['command', 'terminal', 'console', 'command terminal'],
  health: ['health', 'health check', 'system health', 'status check'],
  training: ['training', 'training data', 'training entries', 'ml data'],
  loop: ['loop', 'main loop', 'loop status', 'autonomous loop'],
  scheduler: ['scheduler', 'scheduled tasks', 'cron', 'jobs'],
  inference: ['inference', 'llm', 'model inference', 'ai stats'],
  email: ['email', 'inbox', 'messages', 'mail'],
  channels: ['channels', 'channel status', 'communications'],
  providers: ['providers', 'ai providers', 'model routes', 'routing'],
  tools: ['tools', 'tool registry', 'available tools', 'functions'],
  network: ['network', 'peers', 'peer discovery', 'nodes'],
  audit: ['audit', 'audit trail', 'audit log', 'merkle chain'],
  metering: ['metering', 'budget', 'cost', 'spending'],
  jupyter: ['jupyter', 'jupyter sessions', 'notebook', 'code sessions'],
  sandbox: ['sandbox', 'container', 'docker', 'sandbox execution'],
  sensing: ['sensing', 'sensors', 'health monitor', 'fatigue'],
  media: ['media', 'models', 'image generation', 'generative'],
  mining: ['mining', 'pearl', 'shares', 'mining status'],
  mcp: ['mcp', 'mcp server', 'tools server'],
  video: ['video', 'composer', 'video composition', 'studio'],
  scraper: ['scraper', 'web scraper', 'fetcher', 'crawler'],
  seo: ['seo', 'pagespeed', 'seo tools', 'performance'],
  oauth: ['oauth', 'integrations', 'oauth providers', 'api keys'],
  research: ['research', 'research engine', 'parallel search'],
  migration: ['migration', 'import', 'agent migration'],
}

function parseScrollCommand(text: string): string | null {
  const lower = text.toLowerCase().trim()
  const patterns = [
    /^(?:scroll to|go to|show|open|navigate to|focus on|zoom to)\s+(.+?)$/i,
    /^(?:show me|take me to|switch to)\s+(.+?)$/i,
    /^where\s+is\s+(.+?)$/i,
  ]
  for (const p of patterns) {
    const m = lower.match(p)
    if (m) {
      const target = m[1].trim().replace(/\s+panel$/, '')
      for (const [id, aliases] of Object.entries(PANEL_ALIASES)) {
        if (aliases.some((a) => target === a || target.startsWith(a))) return id
      }
    }
  }
  return null
}

interface HistoryEntry { cmd: string; resp: string; ts: number }

const HISTORY_KEY = 'vector_cmd_history'
const MAX_HISTORY = 50

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveHistory(entries: HistoryEntry[]) {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(entries.slice(0, MAX_HISTORY))) } catch { /* quota exceeded */ }
}

export default function CommandInput() {
  const [text, setText] = useState('')
  const [resp, setResp] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [progress, setProgress] = useState(0)
  const [lastAction, setLastAction] = useState<string | null>(null)
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory())
  const [showHistory, setShowHistory] = useState(false)
  const respRef = useRef('')
  const inputRef = useRef<HTMLInputElement>(null)
  const quickResult = useVectorStore((s) => s.quickResult)
  const setQuickResult = useVectorStore((s) => s.setQuickResult)
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)
  const appMode = useVectorStore((s) => s.mode)
  const addContentWindow = useVectorStore((s) => s.addContentWindow)
  const appModeRef = useRef(appMode)
  const addContentWindowRef = useRef(addContentWindow)
  useEffect(() => { appModeRef.current = appMode }, [appMode])
  useEffect(() => { addContentWindowRef.current = addContentWindow }, [addContentWindow])

  const pushHistory = useCallback((cmd: string, resp: string) => {
    setHistory((prev) => {
      const next = [{ cmd, resp, ts: Date.now() }, ...prev].slice(0, MAX_HISTORY)
      saveHistory(next)
      return next
    })
  }, [])

  useEffect(() => {
    const unsubToken = onTokenReceived((token) => {
      respRef.current += token
      setResp(respRef.current)
      setStreaming(true)
    })
    const unsubDone = onDoneReceived((full) => {
      setResp(full)
      setStreaming(false)
      setSending(false)
      setProgress(0)
      if (lastCmdRef.current) {
        pushHistory(lastCmdRef.current, full)
        if (appModeRef.current === 'JARVIS_MODE') {
          const lower = lastCmdRef.current.toLowerCase()
          if (lower.includes('camera') || lower.includes('webcam') || lower.includes('show desk')) {
            addContentWindowRef.current({ id: `cam-${Date.now()}`, type: 'camera', title: 'CAMERA FEED' })
          } else if (lower.includes('location') || lower.includes('map') || lower.includes('where am i')) {
            addContentWindowRef.current({ id: `map-${Date.now()}`, type: 'map', title: 'LOCATION LOCK' })
          } else {
            addContentWindowRef.current({ id: `resp-${Date.now()}`, type: 'text', title: lastCmdRef.current.slice(0, 30), content: full })
          }
        }
      }
    })
    const unsubError = onErrorReceived((err) => {
      setResp(`ERROR: ${err}`)
      setStreaming(false)
      setSending(false)
      setProgress(0)
    })
    return () => { unsubToken(); unsubDone(); unsubError() }
  }, [])

  useEffect(() => {
    if (!sending || !streaming) return
    const id = setInterval(() => setProgress((p) => Math.min(95, p + Math.random() * 8)), 800)
    return () => clearInterval(id)
  }, [sending, streaming])

  const lastCmdRef = useRef('')

  const scrollToPanel = useVectorStore((s) => s.scrollToPanel)

  const executeCommand = useCallback(async (cmd: string) => {
    if (!cmd.trim() || sending) return

    // Check for scroll commands first (handled locally)
    const scrollId = parseScrollCommand(cmd)
    if (scrollId) {
      scrollToPanel(scrollId)
      setResp(`Scrolling to ${scrollId}...`)
      setText('')
      const labels: Record<string, string> = {
        telemetry: 'Telemetry', systemMetrics: 'System Metrics', events: 'Event Feed',
        compass: 'Compass', modelSwitcher: 'Model Switcher', coreStatus: 'Core Status',
        dailyInfo: 'Daily Briefing', vectorCode: 'VectorCode', districts: 'Districts',
        command: 'Command Terminal',
      }
      pushHistory(cmd, `Navigated to ${labels[scrollId] || scrollId}`)
      return
    }

    lastCmdRef.current = cmd
    setSending(true)
    setResp('')
    setProgress(5)
    setLastAction(null)
    setFeedbackSent(false)
    respRef.current = ''

    // Try WebSocket first (streaming)
    if (sendMessage(cmd)) {
      setText('')
      return
    }

    // Fallback: REST API — all logic handled by backend
    try {
      const d = await api.command(cmd)
      const response = d.response || 'No response'
      setResp(response)
      if (d.action_taken) setLastAction(d.action_taken)
      setProgress(100)
      setText('')
      pushHistory(cmd, response)
      // In JARVIS mode, open response as a content window
      if (appMode === 'JARVIS_MODE') {
        const lower = cmd.toLowerCase()
        if (lower.includes('camera') || lower.includes('webcam') || lower.includes('show desk')) {
          addContentWindow({ id: `cam-${Date.now()}`, type: 'camera', title: 'CAMERA FEED' })
        } else if (lower.includes('location') || lower.includes('map') || lower.includes('where am i')) {
          addContentWindow({ id: `map-${Date.now()}`, type: 'map', title: 'LOCATION LOCK' })
        } else {
          addContentWindow({ id: `resp-${Date.now()}`, type: 'text', title: cmd.slice(0, 30), content: response })
        }
      }
    } catch (e: any) {
      setResp(`ERROR: ${e.message}`)
    }
    setSending(false)
    setProgress(0)
  }, [sending, pushHistory])

  const send = useCallback(() => {
    executeCommand(text)
  }, [text, executeCommand])

  const sendFeedback = async (rating: 1 | 2 | 3 | 4 | 5) => {
    if (!lastAction || feedbackSent) return
    try {
      await api.feedback(lastAction, rating)
      setFeedbackSent(true)
    } catch { /* silent */ }
  }

  const triggerCouncil = async () => {
    if (!text.trim() || sending) return
    setSending(true)
    setResp('Convening council...')
    setProgress(10)
    try {
      const d = await api.council(text.trim(), 'high')
      setResp(d.verdict || 'No verdict')
      setLastAction('council')
      pushHistory(text.trim(), d.verdict || 'No verdict')
      setText('')
    } catch (e: any) {
      setResp(`ERROR: ${e.message}`)
    }
    setSending(false)
    setProgress(0)
  }

  const handleVoiceResult = useCallback((transcript: string, response: string) => {
    if (transcript) {
      setText(transcript)
      executeCommand(transcript)
    }
    if (response && !transcript) {
      setResp(response)
    }
  }, [executeCommand])

  const hasActions = goalsLen > 0

  return (
    <div className="corner-bracket" style={{
      background: 'rgba(5,13,26,0.92)', backdropFilter: 'blur(16px)',
      border: '1px solid rgba(0,212,255,0.12)',
      boxShadow: '0 0 40px rgba(0,212,255,0.04), inset 0 0 20px rgba(0,212,255,0.02)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '5px 12px', borderBottom: '1px solid rgba(0,212,255,0.06)',
        fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.15em',
      }}>
        <span>COMMAND TERMINAL</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {streaming && (
            <svg width="32" height="14" viewBox="0 0 32 14">
              {Array.from({ length: 16 }, (_, i) => (
                <rect key={i} x={i * 2} y={0} width="1.5" height="14" fill="#81D4FA" opacity="0.6" rx="0.5">
                  <animate attributeName="height" values="2;12;2" dur={`${0.3 + i * 0.04}s`} repeatCount="indefinite" />
                  <animate attributeName="y" values="6;1;6" dur={`${0.3 + i * 0.04}s`} repeatCount="indefinite" />
                </rect>
              ))}
            </svg>
          )}
          <span style={{ color: streaming ? '#81D4FA' : '#1a6688' }}>
            {streaming ? 'PROCESSING' : 'STANDBY'}
          </span>
          <button
            aria-label="Command history"
            title="Command history"
            onClick={() => setShowHistory((p) => !p)}
            style={{
              background: 'transparent', border: 'none',
              color: showHistory ? '#4FC3F7' : '#1a4466',
              cursor: 'pointer', fontFamily: "'Orbitron', sans-serif", fontSize: 9,
              padding: '2px 6px', transition: 'all 0.3s',
            }}
          >
            ⌚
          </button>
        </div>
      </div>

      {/* Input row */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 12px', gap: 8 }}>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13,
          color: streaming ? '#81D4FA' : hasActions ? '#4FC3F7' : '#4FC3F7',
          filter: `drop-shadow(0 0 ${streaming ? 12 : 5}px currentColor)`,
          transition: 'all 0.4s ease', minWidth: 14,
        }}>
          {streaming ? '⟳' : hasActions ? '●' : '⚡'}
        </span>
        <input
          ref={inputRef}
          style={{
            flex: 1, background: 'transparent', border: 'none',
            borderBottom: `1px solid ${streaming ? 'rgba(0,255,212,0.25)' : 'rgba(0,212,255,0.15)'}`,
            color: '#c8e8ff', fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
            padding: '6px 4px', outline: 'none', transition: 'all 0.3s',
            letterSpacing: '0.02em',
          }}
          placeholder="Speak your command, sir..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) send()
            if (e.key === 'Enter' && e.shiftKey) triggerCouncil()
          }}
          disabled={sending}
          aria-label="Command input"
        />
        {/* Council button */}
        <button
          title="Convene LLM Council (Shift+Enter)"
          aria-label="Convene council"
          style={{
            background: 'transparent',
            border: '1px solid rgba(191,95,255,0.25)',
            color: '#64B5F6', fontFamily: "'Orbitron', sans-serif", fontSize: 9,
            padding: '7px 10px', cursor: 'pointer', letterSpacing: '0.1em',
            transition: 'all 0.3s', opacity: sending ? 0.4 : 1,
          }}
          onClick={triggerCouncil}
          disabled={sending}
        >
          ⚖
        </button>
        {/* Voice input button */}
        <VoiceInput onResult={handleVoiceResult} />

        {/* Execute button */}
        <button
          aria-label="Send command"
          style={{
            background: 'transparent',
            border: `1px solid ${streaming ? 'rgba(0,255,212,0.35)' : 'rgba(0,212,255,0.25)'}`,
            color: streaming ? '#81D4FA' : '#4FC3F7',
            fontFamily: "'Orbitron', sans-serif", fontSize: 10,
            padding: '7px 18px', cursor: 'pointer', letterSpacing: '0.12em',
            transition: 'all 0.3s', opacity: sending ? 0.5 : 1,
          }}
          onClick={send}
          disabled={sending}
        >
          {sending ? (streaming ? '⟳' : '...') : '▶ EXEC'}
        </button>
      </div>

      {/* Progress bar */}
      {(hasActions || sending) && (
        <div style={{ padding: '0 12px 4px' }}>
          <div style={{ height: 2, background: 'rgba(0,212,255,0.06)', borderRadius: 1, overflow: 'hidden' }}>
            <div style={{
              width: `${progress}%`, height: '100%',
              background: 'linear-gradient(90deg, #81D4FA, #4FC3F7)',
              boxShadow: '0 0 8px #81D4FA', transition: 'width 0.5s ease',
            }} />
          </div>
        </div>
      )}

      {/* History dropdown */}
      {showHistory && history.length > 0 && (
        <div style={{
          maxHeight: 200, overflowY: 'auto',
          borderTop: '1px solid rgba(0,212,255,0.06)',
          background: 'rgba(4,12,24,0.95)',
        }}>
          {history.slice(0, 20).map((h, i) => (
            <div
              key={h.ts}
              onClick={() => { setText(h.cmd); setShowHistory(false); inputRef.current?.focus() }}
              style={{
                padding: '5px 12px', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center',
                borderBottom: i < Math.min(history.length, 20) - 1 ? '1px solid rgba(0,212,255,0.03)' : 'none',
                transition: 'background 0.2s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(0,212,255,0.04)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{
                fontFamily: "'Orbitron', sans-serif", fontSize: 6, color: '#1a4466',
                minWidth: 40,
              }}>
                {new Date(h.ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' })}
              </span>
              <span style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
                color: '#6a9abf', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
              }}>
                {h.cmd}
              </span>
              <span style={{
                fontFamily: "'Orbitron', sans-serif", fontSize: 6, color: '#1a4466', opacity: 0.5,
              }}>
                ↲
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Response area */}
      {resp && (
        <div style={{
          padding: '8px 14px 10px',
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
          color: '#a8d8f0', borderTop: '1px solid rgba(0,212,255,0.06)',
          maxHeight: 280, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          lineHeight: 1.6,
        }}>
          <span style={{ color: '#4FC3F7', marginRight: 8, fontFamily: "'Orbitron', sans-serif", fontSize: 8 }}>
            VECTOR:
          </span>
          {resp}
          {streaming && (
            <span style={{
              display: 'inline-block', width: 7, height: 13,
              background: '#81D4FA', marginLeft: 3, verticalAlign: 'text-bottom',
              animation: 'v-pulse 0.5s infinite',
            }} />
          )}
        </div>
      )}

      {/* Feedback row — only shown after a completed action */}
      {lastAction && !streaming && !feedbackSent && (
        <div style={{
          padding: '4px 14px 8px', borderTop: '1px solid rgba(0,212,255,0.04)',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a6688', letterSpacing: '0.1em', marginRight: 4 }}>
            RATE:
          </span>
          {([1, 2, 3, 4, 5] as const).map((r) => (
            <button
              key={r}
              onClick={() => sendFeedback(r)}
              title={['Poor', 'Bad', 'OK', 'Good', 'Excellent'][r - 1]}
              style={{
                background: 'transparent',
                border: '1px solid rgba(0,212,255,0.15)',
                color: r >= 4 ? '#4FC3F7' : r === 3 ? '#42A5F5' : '#ff6644',
                fontFamily: "'Orbitron', sans-serif", fontSize: 8,
                padding: '3px 7px', cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              {r}
            </button>
          ))}
          <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#1a4466', marginLeft: 4 }}>
            {lastAction.toUpperCase()}
          </span>
        </div>
      )}
      {feedbackSent && (
        <div style={{ padding: '4px 14px 6px', fontFamily: "'Orbitron', sans-serif", fontSize: 7, color: '#4FC3F7', letterSpacing: '0.1em' }}>
          ✓ FEEDBACK RECORDED
        </div>
      )}

      {/* Quick result */}
      {quickResult && (
        <div style={{ borderTop: '1px solid rgba(0,207,255,0.05)', padding: '6px 14px', position: 'relative' }}>
          <button onClick={() => setQuickResult(null)} style={{ position: 'absolute', top: 4, right: 8, background: 'transparent', border: 'none', color: '#3388aa', cursor: 'pointer', fontFamily: "'Orbitron', sans-serif", fontSize: 8 }}>✕</button>
          <div style={{ fontFamily: "'Orbitron', sans-serif", fontSize: 8, color: '#3388aa', letterSpacing: '0.1em', marginBottom: 4 }}>{quickResult.title}</div>
          {quickResult.lines.map((line, i) => (
            <div key={i} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#aaddff', padding: '2px 0' }}>{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}
