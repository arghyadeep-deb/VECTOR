import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import DistrictBuilding from './DistrictBuilding'
import AgentDot from './AgentDot'
import ParticleSystem from './ParticleSystem'
import { useCityStore } from '../hooks/useCityStore'
import { useVectorStore } from '../store/vectorStore'

const GRID_SIZE = 20
const GRID_DIVISIONS = 40

const DEFAULT_DISTRICTS = [
  { name: 'Governance', hp: 850, color: '#4488FF', position: [0, 0, -7] as [number, number, number], agents: ['Aegis', 'Prime'] },
  { name: 'Security', hp: 720, color: '#FF4444', position: [6.5, 0, -3] as [number, number, number], agents: ['Shield', 'Watch'] },
  { name: 'Coding', hp: 910, color: '#44FF88', position: [6.5, 0, 3] as [number, number, number], agents: ['Nexus', 'Forge'] },
  { name: 'Health', hp: 680, color: '#BB66FF', position: [0, 0, 7] as [number, number, number], agents: ['Pulse', 'Vitals'] },
  { name: 'Memory', hp: 780, color: '#44DDDD', position: [-6.5, 0, 3] as [number, number, number], agents: ['Echo', 'Lumen'] },
  { name: 'Research', hp: 650, color: '#FF8800', position: [-6.5, 0, -3] as [number, number, number], agents: ['Vertex', 'Datum'] },
  { name: 'Finance', hp: 590, color: '#FFDD44', position: [3.5, 0, 6] as [number, number, number], agents: ['Coin', 'Ledger'] },
]

function GroundGrid() {
  const gridRef = useRef<THREE.GridHelper>(null!)

  useFrame(({ clock }) => {
    if (gridRef.current) {
      gridRef.current.position.z = (clock.getElapsedTime() * 0.5) % 1
    }
  })

  return (
    <gridHelper
      ref={gridRef}
      args={[GRID_SIZE, GRID_DIVISIONS, '#00CFFF', '#003344']}
      position={[0, -0.5, 0]}
    />
  )
}

function GroundPlane() {
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(GRID_SIZE, GRID_SIZE)
    g.rotateX(-Math.PI / 2)
    return g
  }, [])

  return (
    <mesh geometry={geo} position={[0, -0.5, 0]}>
      <meshBasicMaterial color="#050a15" transparent opacity={0.8} />
    </mesh>
  )
}

function AmbientParticles() {
  const count = 500
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3)
    for (let i = 0; i < count * 3; i++) {
      arr[i] = (Math.random() - 0.5) * 30
    }
    return arr
  }, [])

  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    return g
  }, [positions])

  return (
    <points geometry={geo}>
      <pointsMaterial
        size={0.03}
        color="#00CFFF"
        transparent
        opacity={0.3}
        sizeAttenuation
      />
    </points>
  )
}

export default function CityEnvironment() {
  const districts = useCityStore((s) => s.districts)
  const selectedDistrict = useCityStore((s) => s.selectedDistrict)
  const selectDistrict = useCityStore((s) => s.selectDistrict)
  const agents = useVectorStore((s) => s.agents)

  const districtList = useMemo(() => {
    if (districts.size > 0) {
      return Array.from(districts.values())
    }
    return DEFAULT_DISTRICTS
  }, [districts])

  const particleEvents = useMemo(() => {
    return agents.slice(0, 5).map((a, i) => ({
      from: DEFAULT_DISTRICTS[i % DEFAULT_DISTRICTS.length].position,
      to: DEFAULT_DISTRICTS[(i + 1) % DEFAULT_DISTRICTS.length].position,
      timestamp: Date.now() + i * 500,
      type: 'communication',
    }))
  }, [agents])

  return (
    <>
      <ambientLight intensity={0.15} />
      <directionalLight position={[10, 15, 10]} intensity={0.6} color="#4488ff" />
      <directionalLight position={[-10, 5, -10]} intensity={0.2} color="#ff4488" />

      <GroundPlane />
      <GroundGrid />
      <AmbientParticles />

      {districtList.map((d) => (
        <group key={d.name}>
          <DistrictBuilding
            position={d.position}
            height={d.hp}
            color={d.color}
            label={d.name}
            agents={d.agents}
            isSelected={selectedDistrict === d.name}
            onClick={(name) => selectDistrict(selectedDistrict === name ? null : name)}
          />
          <AgentDot
            count={Math.max(1, Math.floor(d.agents.length * 2))}
            radius={0.8}
            color={d.color}
          />
        </group>
      ))}

      <ParticleSystem events={particleEvents} />
    </>
  )
}
