import { useState, useRef, useCallback } from 'react'
import { api } from '../lib/api'

interface Props {
  onResult: (transcript: string, response: string) => void
}

export default function VoiceInput({ onResult }: Props) {
  const [recording, setRecording] = useState(false)
  const [sending, setSending] = useState(false)
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      mediaRecorder.current = mr
      chunks.current = []

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data)
      }

      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks.current, { type: 'audio/webm' })
        if (blob.size < 100) return
        setSending(true)
        try {
          const result = await api.voice(blob)
          if (result.transcript) onResult(result.transcript, result.response)
        } catch {
          onResult('', 'Voice processing failed')
        }
        setSending(false)
      }

      mr.start()
      setRecording(true)
    } catch {
      onResult('', 'Microphone access denied')
    }
  }, [onResult])

  const stopRecording = useCallback(() => {
    if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
      mediaRecorder.current.stop()
    }
    setRecording(false)
  }, [])

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
