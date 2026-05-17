import { useEffect, useRef } from 'react'

interface Message { role: string; content: string; ts: string }
interface Props { messages: Message[] }

export function ChatPanel({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      {messages.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--jarvis-text-muted)', marginTop: 40 }}>
          <div style={{ fontSize: '2rem', marginBottom: 8, opacity: 0.3 }}>◈</div>
          <div className="label">VECTOR INTERFACE READY</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--jarvis-text-dim)', marginTop: 4 }}>
            All systems operational. Awaiting input.
          </div>
        </div>
      )}
      {messages.map((msg, i) => (
        <div key={i} style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
          gap: 2,
        }}>
          <div style={{
            maxWidth: '85%',
            padding: '8px 12px',
            background: msg.role === 'user' ? 'rgba(0,212,255,0.08)' : 'rgba(26,143,255,0.06)',
            border: `1px solid ${msg.role === 'user' ? 'rgba(0,212,255,0.3)' : 'rgba(26,143,255,0.2)'}`,
            borderRadius: msg.role === 'user' ? '8px 8px 2px 8px' : '8px 8px 8px 2px',
            fontSize: '0.8rem',
            lineHeight: 1.5,
            color: 'var(--jarvis-text)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {msg.content}
          </div>
          <span style={{ fontSize: '0.6rem', color: 'var(--jarvis-text-muted)' }}>
            {msg.role === 'user' ? 'ARGHYADEEP' : 'VECTOR'} · {msg.ts}
          </span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
