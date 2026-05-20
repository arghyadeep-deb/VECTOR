import { useEffect, useRef, useState } from 'react'

interface Props { windowId?: string }

export default function CameraView({ windowId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let stream: MediaStream | null = null
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .catch(() => navigator.mediaDevices.getUserMedia({ video: true, audio: false }))
      .then((s) => {
        stream = s
        if (videoRef.current) {
          videoRef.current.srcObject = s
          videoRef.current.play()
        }
      })
      .catch((e) => setError(`Camera unavailable: ${e.message}`))
    return () => { stream?.getTracks().forEach(t => t.stop()) }
  }, [])

  if (error) {
    return (
      <div style={{
        width: '100%', height: '100%', display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: '#000',
        fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
        color: 'rgba(0,207,255,0.5)',
      }}>
        {error}
      </div>
    )
  }

  return (
    <video ref={videoRef} autoPlay playsInline muted
      style={{ width: '100%', height: '100%', objectFit: 'cover', background: '#000' }} />
  )
}
