import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

function latLngToVec(lat: number, lng: number, r: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lng + 180) * (Math.PI / 180)
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  )
}

interface Props {
  fromLat: number
  fromLng: number
  toLat: number
  toLng: number
  color: string
  progress: number
  radius?: number
}

export default function FlightArc({ fromLat, fromLng, toLat, toLng, color, progress, radius = 2.15 }: Props) {
  const ref = useRef<THREE.Mesh>(null!)
  const arcPoints = useMemo(() => {
    const a = latLngToVec(fromLat, fromLng, radius)
    const b = latLngToVec(toLat, toLng, radius)
    const mid = a.clone().add(b).multiplyScalar(0.5)
    const dist = a.distanceTo(b)
    mid.normalize().multiplyScalar(radius + dist * 0.3)
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b)
    return curve.getPoints(32)
  }, [fromLat, fromLng, toLat, toLng, radius])

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    const pos = new Float32Array(arcPoints.length * 3)
    arcPoints.forEach((p, i) => {
      pos[i * 3] = p.x
      pos[i * 3 + 1] = p.y
      pos[i * 3 + 2] = p.z
    })
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    return g
  }, [arcPoints])

  useFrame(() => {
    const visibleCount = Math.max(2, Math.floor(arcPoints.length * progress))
    const pos = geometry.attributes.position.array as Float32Array
    for (let i = 0; i < arcPoints.length; i++) {
      const show = i < visibleCount ? 1 : 0
      pos[i * 3] = arcPoints[i].x
      pos[i * 3 + 1] = arcPoints[i].y
      pos[i * 3 + 2] = arcPoints[i].z
    }
    geometry.setDrawRange(0, visibleCount)
    geometry.attributes.position.needsUpdate = true
  })

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={color} transparent opacity={0.6 * progress} />
    </lineSegments>
  )
}
