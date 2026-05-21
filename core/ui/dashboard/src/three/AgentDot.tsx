import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface Props {
  count: number
  radius: number
  color: string
}

export default function AgentDot({ count, radius, color }: Props) {
  const groupRef = useRef<THREE.Group>(null!)

  const dots = useMemo(() => {
    const arr: Array<{ angle: number; speed: number; height: number; phase: number }> = []
    for (let i = 0; i < count; i++) {
      arr.push({
        angle: (i / count) * Math.PI * 2 + Math.random() * 0.2,
        speed: 0.3 + Math.random() * 0.4,
        height: (Math.random() - 0.5) * 1.5,
        phase: Math.random() * Math.PI * 2,
      })
    }
    return arr
  }, [count])

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3)
    return arr
  }, [count])

  const pointRef = useRef<THREE.Points>(null!)

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    for (let i = 0; i < count; i++) {
      const d = dots[i]
      const a = d.angle + t * d.speed
      const r = radius + Math.sin(t * d.speed + d.phase) * 0.05
      positions[i * 3] = Math.cos(a) * r
      positions[i * 3 + 1] = d.height + Math.sin(t * d.speed * 0.7 + d.phase) * 0.2
      positions[i * 3 + 2] = Math.sin(a) * r
    }
    pointRef.current.geometry.attributes.position.needsUpdate = true
  })

  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return g
  }, [positions])

  return (
    <group ref={groupRef}>
      <points ref={pointRef} geometry={geo}>
        <pointsMaterial
          size={0.08}
          color={color}
          transparent
          opacity={0.9}
          sizeAttenuation
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  )
}
