'use client';
import { useEffect, useState, useCallback, useRef } from 'react';
import Sidebar from '@/components/hud/Sidebar';
import { api, formatTs, type CouncilResponse, type MemoryEvent } from '@/lib/api';

interface Message { role: 'user' | 'council'; content: string; confidence?: number; ts: string; }

export default function CouncilPage() {
  const [question,  setQuestion]   = useState('');
  const [stakes,    setStakes]     = useState<'medium'|'high'|'critical'>('medium');
  const [messages,  setMessages]   = useState<Message[]>([]);
  const [history,   setHistory]    = useState<MemoryEvent[]>([]);
  const [thinking,  setThinking]   = useState(false);
  const [error,     setError]      = useState('');
  const [voiceStatus, setVoiceStatus] = useState<any>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadHistory = useCallback(async () => {
    try {
      const [d, v] = await Promise.all([api.councilHistory(8), api.voiceStatus()]);
      setHistory(d.sessions ?? []);
      setVoiceStatus(v);
    } catch {}
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const submit = async () => {
    if (!question.trim() || thinking) return;
    const q = question.trim();
    setQuestion('');
    setMessages(prev => [...prev, { role: 'user', content: q, ts: new Date().toISOString() }]);
    setThinking(true);
    setError('');
    try {
      const r: CouncilResponse = await api.council({ question: q, stakes });
      setMessages(prev => [...prev, {
        role: 'council',
        content: r.chairman_decision ?? r.decision,
        confidence: r.confidence,
        ts: new Date().toISOString(),
      }]);
      loadHistory();
    } catch (e: unknown) {
      setError((e as Error).message ?? 'Council unavailable');
      setMessages(prev => [...prev, { role: 'council', content: '⚠ Council members unavailable. Ensure the backend is running with Ollama models loaded.', ts: new Date().toISOString() }]);
    } finally { setThinking(false); }
  };

  return (
    <div className="hud-layout">
      <Sidebar />
      <main className="hud-main">

        <div className="page-header">
          <div>
            <div className="page-title">COUNCIL DELIBERATION <span>// MOD-005-CNC</span></div>
            <div style={{ fontFamily: 'var(--font-label)', fontSize: 9, color: 'var(--on-muted)', marginTop: 2 }}>
              4-MODEL PARALLEL REASONING · CHAIRMAN SYNTHESIS · TRAINING DATA CAPTURE
            </div>
          </div>
          {error && <span className="chip chip-red">⚠ LLM OFFLINE</span>}
        </div>

        <div className="hud-grid-2" style={{ alignItems: 'flex-start' }}>

          {/* Left: Deliberation thread */}
          <div className="module" style={{ padding: 0, display: 'flex', flexDirection: 'column' }}>
            <div className="corner-tl" /><div className="corner-br" />
            <div className="module-header">
              <span>
                <span className="dot dot-cyan" style={{ marginRight: 6 }} />
                SESSION // DELIBERATING
              </span>
              <span className="mod-id">SES-{messages.length.toString().padStart(4,'0')}</span>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', maxHeight: 440, padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              {messages.length === 0 && (
                <div style={{ padding: '30px 0', textAlign: 'center' }}>
                  <div className="loading-text">COUNCIL AWAITING DIRECTIVE...</div>
                  <div style={{ marginTop: 12, fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--on-muted)' }}>
                    Ask a high-stakes question to initiate deliberation.
                  </div>
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                  <div className="flex items-center gap-2">
                    {m.role === 'council' && <span className="chip chip-cyan" style={{ fontSize: 8 }}>CHAIRMAN</span>}
                    <span style={{ fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--outline)' }}>{formatTs(m.ts)}</span>
                    {m.role === 'user' && <span className="chip chip-muted" style={{ fontSize: 8 }}>YOU</span>}
                  </div>
                  <div style={{
                    maxWidth: '85%',
                    padding: '10px 14px',
                    background: m.role === 'user' ? 'rgba(0,255,255,0.08)' : 'rgba(35,44,43,0.9)',
                    border: `1px solid ${m.role === 'user' ? 'rgba(0,255,255,0.3)' : 'var(--outline-dim)'}`,
                    fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--on-surface)', lineHeight: 1.6,
                  }}>
                    {m.content}
                    {m.confidence !== undefined && (
                      <div style={{ marginTop: 8, fontFamily: 'var(--font-label)', fontSize: 8, color: 'var(--on-muted)' }}>
                        CONFIDENCE: <span style={{ color: m.confidence > 0.7 ? 'var(--cyan)' : 'var(--amber)' }}>{Math.round(m.confidence * 100)}%</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {thinking && (
                <div className="animate-in">
                  <span className="chip chip-amber" style={{ fontSize: 8 }}>DELIBERATING</span>
                  <div style={{ display: 'flex', gap: 4, marginTop: 8 }}>
                    {Array.from({ length: 12 }, (_, i) => (
                      <div key={i} className="waveform-bar" style={{ animationDelay: `${i * 0.1}s`, height: 18 }} />
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div style={{ borderTop: '1px solid var(--outline-dim)', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="flex gap-2 items-center">
                <span className="font-label" style={{ fontSize: 9, color: 'var(--on-muted)' }}>STAKES:</span>
                {(['medium','high','critical'] as const).map(s => (
                  <button key={s} onClick={() => setStakes(s)}
                    className={`chip ${stakes === s ? (s === 'critical' ? 'chip-red' : s === 'high' ? 'chip-amber' : 'chip-cyan') : 'chip-muted'}`}
                    style={{ cursor: 'pointer', fontSize: 9 }}>
                    {s.toUpperCase()}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <input className="input-hud flex-1" placeholder="ISSUE DIRECTIVE..." value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && submit()} />
                <button className="btn btn-primary" onClick={submit} disabled={thinking || !question.trim()} style={{ fontSize: 9 }}>
                  {thinking ? '...' : 'SEND'}
                </button>
              </div>
            </div>
          </div>

          {/* Right: Voice pipeline + History */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

            {/* Voice pipeline */}
            <div className="module" style={{ padding: 0 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>VOICE PIPELINE</span><span className="mod-id">MOD-006-VCE</span></div>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div className="flex items-center gap-3">
                  <span className={`chip ${voiceStatus?.stt_status === 'active' ? 'chip-cyan' : 'chip-muted'}`} style={{ fontSize: 8 }}>
                    ● {voiceStatus?.stt_status === 'active' ? 'LISTENING' : 'OFFLINE'}
                  </span>
                  <div className="waveform">
                    {Array.from({ length: 10 }, (_, i) => (
                      <div key={i} className="waveform-bar" style={{ animationDelay: `${i * 0.12}s`, opacity: voiceStatus?.stt_status === 'active' ? 1 : 0.3 }} />
                    ))}
                  </div>
                </div>
                {[
                  { label: 'WAKE WORD', value: voiceStatus?.wake_word ?? 'Hey Vector', status: (voiceStatus?.listener_status ?? 'ARMED').toUpperCase(), color: voiceStatus?.listener_status === 'armed' ? 'chip-cyan' : 'chip-muted' },
                  { label: 'STT ENGINE', value: voiceStatus?.stt_engine ?? 'Whisper',   status: (voiceStatus?.stt_status ?? 'ACTIVE').toUpperCase(), color: voiceStatus?.stt_status === 'active' ? 'chip-cyan' : 'chip-muted' },
                  { label: 'TTS ENGINE', value: voiceStatus?.tts_engine ?? 'Kokoro',    status: (voiceStatus?.tts_status ?? 'READY').toUpperCase(),  color: voiceStatus?.tts_status === 'ready' ? 'chip-cyan' : 'chip-muted' },
                ].map(({ label, value, status, color }) => (
                  <div key={label} className="flex items-center justify-between" style={{ padding: '4px 0', borderBottom: '1px solid var(--outline-dim)' }}>
                    <span className="font-label" style={{ fontSize: 8, color: 'var(--on-muted)' }}>{label}</span>
                    <div className="flex items-center gap-2">
                      <span style={{ fontFamily: 'var(--font-data)', fontSize: 11 }}>{value}</span>
                      <span className={`chip ${color}`} style={{ fontSize: 7 }}>{status}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Command history */}
            <div className="module" style={{ padding: 0, flex: 1 }}>
              <div className="corner-tl" /><div className="corner-br" />
              <div className="module-header"><span>COMMAND HISTORY</span><span className="mod-id">MOD-005-HST</span></div>
              <div style={{ overflowY: 'auto', maxHeight: 320 }}>
                {history.length === 0
                  ? <div className="loading-text" style={{ padding: 20, textAlign: 'center' }}>NO SESSIONS FOUND</div>
                  : <table className="data-table">
                    <thead><tr><th>TIME</th><th>SUMMARY</th><th>STATUS</th></tr></thead>
                    <tbody>
                      {history.map((s, i) => (
                        <tr key={i}>
                          <td style={{ whiteSpace: 'nowrap', fontSize: 10 }}>{formatTs(s.timestamp)}</td>
                          <td style={{ fontSize: 11 }} className="truncate">{s.content?.slice(0, 60) ?? '—'}</td>
                          <td><span className="chip chip-cyan" style={{ fontSize: 8 }}>STORED</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>}
              </div>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}
