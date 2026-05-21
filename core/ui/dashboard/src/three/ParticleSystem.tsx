import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const MAX_PARTICLES = 200
const PARTICLE_LIFETIME = 2.0

interface ParticleEvent {
  from: [number, number, number]
  to: [number, number, number]
  timestamp: number
  type: string
}

interface Props {
  events: ParticleEvent[]
}

const TYPE_COLORS: Record<string, string> = {
  communication: '#00CFFF',
  threat: '#FF4444',
  resource: '#44FF88',
  decision: '#FFAA00',
  default: '#8888FF',
}

export default function ParticleSystem({ events }: Props) {
  const pointsRef = useRef<THREE.Points>(null!)
  const stateRef = useRef<Array<{
    active: boolean
    from: [number, number, number]
    to: [number, number, number]
    progress: number
    color: THREE.Color
    startTime: number
  }>>([])

  const { positions, colors } = useMemo(() => {
    const pos = new Float32Array(MAX_PARTICLES * 3)
    const col = new Float32Array(MAX_PARTICLES * 3)
    for (let i = 0; i < MAX_PARTICLES; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 20
      pos[i * 3 + 1] = (Math.random() - 0.5) * 20
      pos[i * 3 + 2] = (Math.random() - 0.5) * 20
    }
    return { positions: pos, colors: col }
  }, [])

  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    return g
  }, [])

  let eventIndex = 0

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const state = stateRef.current

    while (state.length < MAX_PARTICLES && eventIndex < events.length) {
      const ev = events[eventIndex]
      state.push({
        active: true,
        from: ev.from,
        to: ev.to,
        progress: Math.random() * 0.3,
        color: new THREE.Color(TYPE_COLORS[ev.type] || TYPE_COLORS.default),
        startTime: t,
      })
      eventIndex++
    }

    const pos = geo.attributes.position.array as Float32Array
    const col = geo.attributes.color.array as Float32Array

    for (let i = 0; i < MAX_PARTICLES; i++) {
      if (i < state.length && state[i].active) {
        const p = state[i]
        const dt = t - p.startTime
        p.progress += 0.005

        if (p.progress > 1 || dt > PARTICLE_LIFETIME) {
          if (eventIndex < events.length) {
            const ev = events[eventIndex]
            p.from = ev.from
            p.to = ev.to
            p.progress = 0
            p.startTime = t
            p.color = new THREE.Color(TYPE_COLORS[ev.type] || TYPE_COLORS.default)
            eventIndex++
          } else {
            p.active = false
          }
        }

        const prog = p.progress
        const inv = 1 - prog
        pos[i * 3] = p.from[0] * inv + p.to[0] * prog + Math.sin(prog * Math.PI) * 2
        pos[i * 3 + 1] = p.from[1] * inv + p.to[1] * prog + Math.sin(prog * Math.PI) * 3
        pos[i * 3 + 2] = p.from[2] * inv + p.to[2] * prog

        col[i * 3] = p.color.r * (1 - prog * 0.5)
        col[i * 3 + 1] = p.color.g * (1 - prog * 0.5)
        col[i * 3 + 2] = p.color.b * (1 - prog * 0.5)
      } else {
        pos[i * 3] = (Math.random() - 0.5) * 30
        pos[i * 3 + 1] = -10
        pos[i * 3 + 2] = (Math.random() - 0.5) * 30
      }
    }

    geo.attributes.position.needsUpdate = true
    geo.attributes.color.needsUpdate = true
  })

  return (
    <points ref={pointsRef} geometry={geo} frustumCulled={false}>
      <pointsMaterial
        size={0.15}
        vertexColors
        transparent
        opacity={0.8}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  )
}
