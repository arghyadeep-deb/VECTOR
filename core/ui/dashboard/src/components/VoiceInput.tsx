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
  const setVoiceState = useVectorStore((s) => s.setVoiceState)

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
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
    setRecording(false)
    setVoiceState('processing')
  }, [setVoiceState])

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
