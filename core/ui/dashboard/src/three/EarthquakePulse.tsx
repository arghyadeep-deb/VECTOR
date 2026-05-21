import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

function latLngToPos(lat: number, lng: number, r: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  )
}

interface Props {
  lat: number
  lng: number
  magnitude: number
  timestamp: number
  radius?: number
}

export default function EarthquakePulse({ lat, lng, magnitude, timestamp, radius = 2.15 }: Props) {
  const ref = useRef<THREE.Mesh>(null!)
  const startTime = useRef(Date.now())

  const pos = latLngToPos(lat, lng, radius)

  useFrame(() => {
    const elapsed = (Date.now() - startTime.current) / 1000
    const life = Math.min(elapsed / 3, 1)
    const scale = life * magnitude * 0.3

    if (ref.current) {
      ref.current.scale.setScalar(1 + scale)
      const mat = ref.current.material as THREE.MeshBasicMaterial
      mat.opacity = Math.max(0, 0.6 * (1 - life))
    }
  })

  return (
    <mesh ref={ref} position={pos} rotation={[Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.01, 0.03, 32]} />
      <meshBasicMaterial
        color="#FF4444"
        transparent
        opacity={0.6}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  )
}
