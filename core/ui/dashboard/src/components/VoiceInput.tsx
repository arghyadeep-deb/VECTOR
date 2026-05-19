import { useState, useRef, useCallback } from 'react'
import { useVectorStore } from '../store/vectorStore'

interface Props {
  onResult: (transcript: string, response: string) => void
}

export default function VoiceInput({ onResult }: Props) {
  const [recording, setRecording] = useState(false)
  const [sending, setSending] = useState(false)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const ws = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rafRef = useRef<number>(0)
  const setVoiceState = useVectorStore((s) => s.setVoiceState)
  const setAudioLevel = useVectorStore((s) => s.setAudioLevel)

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Wire real microphone amplitude to the store for VoiceWaveform
      const audioCtx = new AudioContext()
      audioCtxRef.current = audioCtx
      const src = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      src.connect(analyser)
      analyserRef.current = analyser
      const buf = new Float32Array(analyser.frequencyBinCount)
      const tick = () => {
        analyser.getFloatTimeDomainData(buf)
        const rms = Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length)
        setAudioLevel(Math.min(1, rms * 8))
        rafRef.current = requestAnimationFrame(tick)
      }
      rafRef.current = requestAnimationFrame(tick)

      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      mediaRecorder.current = mr

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = `${protocol}//${window.location.host}/ws/voice/stream`
      const socket = new WebSocket(url)
      ws.current = socket

      socket.onopen = () => {
        mr.ondataavailable = (e) => {
          if (e.data.size > 0 && socket.readyState === WebSocket.OPEN) {
            socket.send(e.data)
          }
        }

        mr.onstop = () => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'end' }))
          }
          setVoiceState('processing')
        }

        mr.start()
        setRecording(true)
        setVoiceState('listening')
      }

      socket.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.type === 'transcript') {
            setVoiceState('processing')
            onResult(msg.text, '')
          } else if (msg.type === 'response') {
            setVoiceState('speaking')
            onResult('', msg.text)
          } else if (msg.type === 'audio') {
            setVoiceState('speaking')
          } else if (msg.type === 'done') {
            setVoiceState('idle')
            socket.close()
          } else if (msg.type === 'error') {
            setVoiceState('idle')
            onResult('', `Voice error: ${msg.text}`)
          }
        } catch { /* ignore parse errors */ }
      }

      socket.onerror = () => {
        setVoiceState('idle')
        onResult('', 'WebSocket connection failed')
      }

      socket.onclose = () => setVoiceState('idle')
    } catch {
      setVoiceState('idle')
      onResult('', 'Microphone access denied')
    }
  }, [onResult, setVoiceState])

  const stopRecording = useCallback(() => {
    if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
      mediaRecorder.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
    }
    // Teardown Web Audio analyser
    cancelAnimationFrame(rafRef.current)
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    analyserRef.current = null
    setAudioLevel(0)
    setRecording(false)
    setVoiceState('processing')
  }, [setVoiceState, setAudioLevel])

  const toggle = useCallback(() => {
    if (recording) stopRecording()
    else startRecording()
  }, [recording, startRecording, stopRecording])

  return (
    <button
      aria-label={recording ? 'Stop recording' : 'Start voice input'}
      title={recording ? 'Stop recording' : 'Voice input'}
      onClick={toggle}
      disabled={sending}
      style={{
        background: 'transparent',
        border: `1px solid ${recording ? 'rgba(255,60,60,0.5)' : sending ? 'rgba(79,195,247,0.15)' : 'rgba(0,212,255,0.25)'}`,
        color: recording ? '#FF3D3D' : sending ? '#4FC3F7' : '#4FC3F7',
        fontFamily: "'Orbitron', sans-serif", fontSize: 14,
        padding: '6px 10px', cursor: 'pointer',
        transition: 'all 0.3s',
        position: 'relative',
      }}
    >
      {sending ? '⟳' : recording ? '◉' : '🎤'}
      {recording && (
        <span style={{
          position: 'absolute', top: -2, right: -2,
          width: 6, height: 6, borderRadius: '50%',
          background: '#FF3D3D',
          animation: 'v-pulse 0.5s infinite',
        }} />
      )}
    </button>
  )
}
