import { useState, useEffect, useRef } from 'react'
import { useVectorStore } from '../store/vectorStore'
import { api } from '../lib/api'
import { sendMessage, onTokenReceived, onDoneReceived, onErrorReceived } from '../lib/websocket'

export default function CommandInput() {
  const [text, setText] = useState('')
  const [resp, setResp] = useState('')
  const [sending, setSending] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [progress, setProgress] = useState(0)
  const [lastAction, setLastAction] = useState<string | null>(null)
  const [feedbackSent, setFeedbackSent] = useState(false)
  const respRef = useRef('')
  const inputRef = useRef<HTMLInputElement>(null)
  const quickResult = useVectorStore((s) => s.quickResult)
  const setQuickResult = useVectorStore((s) => s.setQuickResult)
  const goalsLen = useVectorStore((s) => s.goals?.immediate_actions?.length ?? 0)

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

  const send = async () => {
    if (!text.trim() || sending) return
    const cmd = text.trim()
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
      setResp(d.response || 'No response')
      if (d.action_taken) setLastAction(d.action_taken)
      setProgress(100)
      setText('')
    } catch (e: any) {
      setResp(`ERROR: ${e.message}`)
    }
    setSending(false)
    setProgress(0)
  }

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
      setText('')
    } catch (e: any) {
      setResp(`ERROR: ${e.message}`)
    }
    setSending(false)
    setProgress(0)
  }

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
