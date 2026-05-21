import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import FlightArc from './FlightArc'
import EarthquakePulse from './EarthquakePulse'
import { useGlobeStore } from '../hooks/useGlobeStore'

function generateEarthTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 1024
  canvas.height = 512
  const ctx = canvas.getContext('2d')!

  const gradient = ctx.createRadialGradient(512, 256, 0, 512, 256, 400)
  gradient.addColorStop(0, '#0a3a5a')
  gradient.addColorStop(0.3, '#0d4b76')
  gradient.addColorStop(0.6, '#1a5a3a')
  gradient.addColorStop(0.8, '#2a6a4a')
  gradient.addColorStop(1, '#061a2e')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 1024, 512)

  for (let i = 0; i < 120; i++) {
    const x = Math.random() * 1024
    const y = Math.random() * 512
    const w = 10 + Math.random() * 50
    const h = 8 + Math.random() * 30
    const shade = 30 + Math.random() * 80
    ctx.fillStyle = `rgba(${shade}, ${shade + 40}, ${shade + 20}, 0.25)`
    ctx.beginPath()
    ctx.ellipse(x, y, w, h, Math.random() * Math.PI, 0, Math.PI * 2)
    ctx.fill()
  }

  for (let i = 0; i < 80; i++) {
    const x = Math.random() * 1024
    const y = Math.random() * 512
    const size = 2 + Math.random() * 8
    ctx.fillStyle = `rgba(50, 120, 50, ${0.08 + Math.random() * 0.15})`
    ctx.beginPath()
    ctx.arc(x, y, size, 0, Math.PI * 2)
    ctx.fill()
  }

  for (let i = 0; i < 20; i++) {
    const x = Math.random() * 1024
    const y = Math.random() * 512
    ctx.fillStyle = `rgba(200, 200, 150, ${0.05 + Math.random() * 0.08})`
    ctx.beginPath()
    ctx.arc(x, y, 15 + Math.random() * 25, 0, Math.PI * 2)
    ctx.fill()
  }

  for (let i = 0; i < 200; i++) {
    const x = Math.random() * 1024
    const y = Math.random() * 512
    ctx.fillStyle = `rgba(100, 180, 255, ${0.03 + Math.random() * 0.06})`
    ctx.beginPath()
    ctx.arc(x, y, 1 + Math.random() * 3, 0, Math.PI * 2)
    ctx.fill()
  }

  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.ClampToEdgeWrapping
  return texture
}

function generateCloudTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 1024
  canvas.height = 512
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'rgba(0,0,0,0)'
  ctx.fillRect(0, 0, 1024, 512)

  for (let i = 0; i < 150; i++) {
    const x = Math.random() * 1024
    const y = Math.random() * 512
    const rx = 20 + Math.random() * 80
    const ry = 10 + Math.random() * 30
    const alpha = 0.03 + Math.random() * 0.07
    ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`
    ctx.beginPath()
    ctx.ellipse(x, y, rx, ry, Math.random() * Math.PI, 0, Math.PI * 2)
    ctx.fill()
  }

  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.ClampToEdgeWrapping
  return texture
}

export default function WorldStateGlobe() {
  const groupRef = useRef<THREE.Group>(null!)
  const earthRef = useRef<THREE.Mesh>(null!)
  const cloudRef = useRef<THREE.Mesh>(null!)
  const glowRef = useRef<THREE.Mesh>(null!)

  const earthTex = useMemo(() => generateEarthTexture(), [])
  const cloudTex = useMemo(() => generateCloudTexture(), [])

  const flightArcs = useGlobeStore((s) => s.flightArcs)
  const pulses = useGlobeStore((s) => s.earthquakePulses)

  const rotVelocity = useRef(0.05)
  const targetRot = useRef(0)

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()

    targetRot.current = t * 0.04
    rotVelocity.current += (0.04 - rotVelocity.current) * 0.01
    groupRef.current.rotation.y = targetRot.current

    if (cloudRef.current) {
      cloudRef.current.rotation.y = t * 0.06
    }

    if (glowRef.current) {
      glowRef.current.scale.setScalar(1 + Math.sin(t * 0.3) * 0.01)
    }

    groupRef.current.position.y = Math.sin(t * 0.15) * 0.2
  })

  return (
    <group ref={groupRef} position={[0, 0, -3]}>
      <mesh ref={earthRef}>
        <sphereGeometry args={[2, 64, 64]} />
        <meshStandardMaterial
          map={earthTex}
          roughness={0.6}
          metalness={0.1}
          transparent
          opacity={0.9}
          emissive="#002244"
          emissiveIntensity={0.15}
        />
      </mesh>

      <mesh>
        <sphereGeometry args={[2.01, 48, 48]} />
        <meshBasicMaterial
          color="#00CFFF"
          wireframe
          transparent
          opacity={0.04}
        />
      </mesh>

      <mesh ref={cloudRef}>
        <sphereGeometry args={[2.06, 32, 32]} />
        <meshBasicMaterial
          map={cloudTex}
          transparent
          opacity={0.15}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      <mesh ref={glowRef}>
        <sphereGeometry args={[2.2, 32, 32]} />
        <meshBasicMaterial
          color="#00CFFF"
          transparent
          opacity={0.04}
          side={THREE.BackSide}
        />
      </mesh>

      {flightArcs.map((arc) => (
        <FlightArc
          key={arc.id}
          fromLat={arc.fromLat}
          fromLng={arc.fromLng}
          toLat={arc.toLat}
          toLng={arc.toLng}
          color={arc.color}
          progress={arc.progress}
        />
      ))}

      {pulses.map((pulse) => (
        <EarthquakePulse
          key={pulse.id}
          lat={pulse.lat}
          lng={pulse.lng}
          magnitude={pulse.magnitude}
          timestamp={pulse.timestamp}
        />
      ))}
    </group>
  )
}
