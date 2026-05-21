import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { ThreeEvent } from '@react-three/fiber'

interface Props {
  position: [number, number, number]
  height: number
  color: string
  label: string
  agents: string[]
  isSelected: boolean
  onClick: (name: string) => void
}

export default function DistrictBuilding({ position, height, color, label, agents, isSelected, onClick }: Props) {
  const meshRef = useRef<THREE.Mesh>(null!)
  const glowRef = useRef<THREE.Mesh>(null!)
  const targetHeight = useRef(height)
  const currentHeight = useRef(height)

  const geometry = useMemo(() => new THREE.BoxGeometry(1.2, 1, 1.2), [])

  const labelRef = useRef<HTMLDivElement>(null)

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    targetHeight.current = height
    currentHeight.current += (targetHeight.current - currentHeight.current) * 0.05

    if (meshRef.current) {
      meshRef.current.scale.y = Math.max(0.1, currentHeight.current / 500)
      meshRef.current.position.y = (Math.max(0.1, currentHeight.current / 500) * 1) / 2
    }

    if (glowRef.current) {
      const glowIntensity = isSelected ? 0.6 + Math.sin(t * 2) * 0.3 : 0.15 + Math.sin(t * 0.5) * 0.05
      glowRef.current.scale.setScalar(1 + (isSelected ? 0.15 + Math.sin(t * 3) * 0.05 : 0))
      const mat = glowRef.current.material as THREE.MeshBasicMaterial
      mat.opacity = glowIntensity
    }

    if (labelRef.current) {
      labelRef.current.style.opacity = isSelected ? '1' : '0.7'
    }
  })

  const handleClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    onClick(label)
  }

  const scaledHeight = Math.max(0.1, height / 500)

  return (
    <group position={position}>
      <mesh
        ref={glowRef}
        position={[0, scaledHeight / 2, 0]}
        onClick={handleClick}
      >
        <boxGeometry args={[1.6, scaledHeight + 0.2, 1.6]} />
        <meshBasicMaterial color={color} transparent opacity={0.08} side={THREE.BackSide} />
      </mesh>

      <mesh
        ref={meshRef}
        position={[0, scaledHeight / 2, 0]}
        geometry={geometry}
        onClick={handleClick}
      >
        <meshStandardMaterial
          color={color}
          roughness={0.4}
          metalness={0.3}
          emissive={color}
          emissiveIntensity={isSelected ? 0.5 : 0.1}
        />
      </mesh>

      <mesh position={[0, 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[2, 2]} />
        <meshBasicMaterial color={color} transparent opacity={isSelected ? 0.15 : 0.04} />
      </mesh>

      <sprite position={[0, scaledHeight + 0.5, 0]} scale={[1.5, 0.6, 1]}>
        <spriteMaterial
          transparent
          opacity={0}
          depthTest={false}
          ref={(m) => {
            if (m && labelRef.current) {
              const canvas = document.createElement('canvas')
              canvas.width = 256
              canvas.height = 64
              const ctx = canvas.getContext('2d')!
              ctx.fillStyle = 'rgba(0,0,0,0)'
              ctx.fillRect(0, 0, 256, 64)
              ctx.fillStyle = isSelected ? '#ffffff' : color
              ctx.font = 'bold 20px JetBrains Mono'
              ctx.textAlign = 'center'
              ctx.fillText(label, 128, 28)
              ctx.fillStyle = 'rgba(255,255,255,0.5)'
              ctx.font = '14px JetBrains Mono'
              ctx.fillText(`${agents.length} agents`, 128, 50)
              const tex = new THREE.CanvasTexture(canvas)
              m.map = tex
              m.opacity = 1
              m.needsUpdate = true
            }
          }}
        />
      </sprite>
    </group>
  )
}
