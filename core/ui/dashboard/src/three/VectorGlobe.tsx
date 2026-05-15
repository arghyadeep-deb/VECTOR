import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

function generateEarthTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 256
  const ctx = canvas.getContext('2d')!

  const gradient = ctx.createRadialGradient(256, 128, 0, 256, 128, 200)
  gradient.addColorStop(0, '#0a2a4a')
  gradient.addColorStop(0.5, '#0d3b66')
  gradient.addColorStop(1, '#061a2e')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 512, 256)

  for (let i = 0; i < 60; i++) {
    const x = Math.random() * 512
    const y = Math.random() * 256
    const size = 3 + Math.random() * 20
    const shade = 20 + Math.random() * 60
    ctx.fillStyle = `rgba(${shade}, ${shade + 40}, ${shade + 30}, 0.3)`
    ctx.beginPath()
    ctx.ellipse(x, y, size * (0.5 + Math.random()), size * (0.3 + Math.random() * 0.4), Math.random() * Math.PI, 0, Math.PI * 2)
    ctx.fill()
  }

  for (let i = 0; i < 40; i++) {
    const x = Math.random() * 512
    const y = Math.random() * 256
    const size = 1 + Math.random() * 5
    ctx.fillStyle = `rgba(60, 120, 60, ${0.1 + Math.random() * 0.2})`
    ctx.beginPath()
    ctx.arc(x, y, size, 0, Math.PI * 2)
    ctx.fill()
  }

  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.ClampToEdgeWrapping
  return texture
}

export default function VectorGlobe() {
  const groupRef = useRef<THREE.Group>(null!)
  const cloudRef = useRef<THREE.Mesh>(null!)
  const texture = useMemo(() => generateEarthTexture(), [])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    groupRef.current.rotation.y = t * 0.05
    if (cloudRef.current) cloudRef.current.rotation.y = t * 0.07
    groupRef.current.position.y = Math.sin(t * 0.2) * 0.3
  })

  return (
    <group ref={groupRef} position={[0, 0, -3]}>
      <mesh>
        <sphereGeometry args={[2, 48, 48]} />
        <meshStandardMaterial
          map={texture}
          roughness={0.7}
          metalness={0.1}
          transparent
          opacity={0.85}
          emissive="#002244"
          emissiveIntensity={0.2}
        />
      </mesh>

      <mesh>
        <sphereGeometry args={[2.01, 32, 32]} />
        <meshBasicMaterial
          color="#00CFFF"
          wireframe
          transparent
          opacity={0.06}
        />
      </mesh>

      <mesh ref={cloudRef}>
        <sphereGeometry args={[2.05, 24, 24]} />
        <meshBasicMaterial
          color="#4488aa"
          transparent
          opacity={0.08}
          side={THREE.DoubleSide}
        />
      </mesh>

      <mesh>
        <sphereGeometry args={[2.15, 16, 16]} />
        <meshBasicMaterial
          color="#00CFFF"
          transparent
          opacity={0.03}
          side={THREE.BackSide}
        />
      </mesh>
    </group>
  )
}
