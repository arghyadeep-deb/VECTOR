import { useRef, useMemo, useState, useEffect } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { useVectorStore } from '../store/vectorStore'
import { Z } from '../lib/zIndex'
import VectorGlobe from './VectorGlobe'

function CoreSphere({ cpuLoad, alert }: { cpuLoad: number; alert: boolean }) {
  const ref = useRef<THREE.Mesh>(null!)
  const matRef = useRef<THREE.MeshPhysicalMaterial>(null!)
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    ref.current.rotation.x = Math.sin(t * 0.15) * 0.1
    ref.current.rotation.y = t * (0.06 + cpuLoad * 0.04)
    ref.current.scale.setScalar(1 + Math.sin(t * 0.6) * 0.02)
    if (matRef.current) {
      matRef.current.emissiveIntensity = alert ? 1.5 + Math.sin(t * 3) * 0.5 : 0.5
      matRef.current.emissive = new THREE.Color(alert ? '#FF3D3D' : '#002244')
      matRef.current.color = new THREE.Color(alert ? '#FF6B6B' : '#00CFFF')
    }
  })
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[0.8, 1]} />
      <meshPhysicalMaterial ref={matRef} roughness={0.05} metalness={0.9} transparent opacity={0.6} emissive="#002244" emissiveIntensity={0.5} />
    </mesh>
  )
}

function CoreWireframe({ alert, avgHp }: { alert: boolean; avgHp: number }) {
  const ref = useRef<THREE.Mesh>(null!)
  const baseOpacity = 0.05 + (avgHp / 1000) * 0.2
  useFrame(({ clock }) => {
    ref.current.rotation.x = Math.sin(clock.getElapsedTime() * 0.12) * 0.15
    ref.current.rotation.y = -clock.getElapsedTime() * (0.04 + (alert ? 0.04 : 0))
  })
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[1.1, 1]} />
      <meshBasicMaterial color={alert ? '#FF3D3D' : '#00CFFF'} wireframe transparent opacity={baseOpacity} />
    </mesh>
  )
}

function GlowSphere() {
  const ref = useRef<THREE.Mesh>(null!)
  useFrame(({ clock }) => { ref.current.scale.setScalar(1 + Math.sin(clock.getElapsedTime() * 0.4) * 0.03) })
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[1.3, 16, 16]} />
      <meshBasicMaterial color="#00CFFF" transparent opacity={0.04} />
    </mesh>
  )
}

function ParticleField({ burst = false }: { burst: boolean }) {
  const ref = useRef<THREE.Points>(null!)
  const count = 200
  const positions = useMemo(() => { const arr = new Float32Array(count * 3); for (let i = 0; i < count * 3; i++) arr[i] = (Math.random() - 0.5) * 30; return arr }, [])
  const velocities = useMemo(() => { const arr = new Float32Array(count); for (let i = 0; i < count; i++) arr[i] = (Math.random() - 0.5) * 0.02; return arr }, [])
  useFrame(({ clock }) => {
    ref.current.rotation.y = clock.getElapsedTime() * 0.02
    if (burst) {
      const positions = ref.current.geometry.attributes.position.array as Float32Array
      for (let i = 0; i < count; i++) {
        positions[i * 3] += velocities[i] * 5
        positions[i * 3 + 1] += velocities[i] * 3
        if (Math.abs(positions[i * 3]) > 15) positions[i * 3] = (Math.random() - 0.5) * 30
        if (Math.abs(positions[i * 3 + 1]) > 15) positions[i * 3 + 1] = (Math.random() - 0.5) * 30
      }
      ref.current.geometry.attributes.position.needsUpdate = true
    }
  })
  return (
    <points ref={ref}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
      <pointsMaterial size={0.05} color="#00CFFF" transparent opacity={burst ? 0.7 : 0.4} sizeAttenuation />
    </points>
  )
}

function SceneContent() {
  const systemMetrics = useVectorStore((s) => s.systemMetrics)
  const events = useVectorStore((s) => s.events)
  const agents = useVectorStore((s) => s.agents)
  const showGlobe = useVectorStore((s) => s.showGlobe)

  const cpuLoad = ((systemMetrics?.cpu_percent ?? 50) / 100)
  const avgHp = agents.length > 0 ? agents.reduce((s, a) => s + a.health_points, 0) / agents.length : 500
  const alert = events.some((e) => {
    const t = e.event_type?.toLowerCase() ?? ''
    return t.includes('error') || t.includes('critical') || t.includes('die')
  })
  const burst = events.slice(0, 3).some((e) => {
    const t = e.event_type?.toLowerCase() ?? ''
    return t.includes('think') || t.includes('process') || t.includes('act')
  })

  return (
    <>
      <ambientLight intensity={0.1} />
      <pointLight position={[5, 5, 5]} intensity={0.8} color="#00CFFF" />
      {showGlobe ? (
        <VectorGlobe />
      ) : (
        <>
          <GlowSphere />
          <CoreSphere cpuLoad={cpuLoad} alert={alert} />
          <CoreWireframe alert={alert} avgHp={avgHp} />
          <ParticleField burst={burst} />
        </>
      )}
      <OrbitControls enablePan={false} enableZoom autoRotate autoRotateSpeed={0.4} minDistance={5} maxDistance={15} />
    </>
  )
}

export default function VectorScene() {
  const [webglFailed, setWebglFailed] = useState(false)

  useEffect(() => {
    try {
      const cvs = document.createElement('canvas')
      const gl = cvs.getContext('webgl') || cvs.getContext('experimental-webgl')
      if (!gl) { setWebglFailed(true); return }
    } catch { setWebglFailed(true) }
  }, [])

  if (webglFailed) {
    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: Z.SCENE,
      }}>
        <style>{`@keyframes pulseBg{0%,100%{opacity:0.3}50%{opacity:0.6}}`}</style>
        <div style={{
          position: 'absolute', top: '50%', left: '50%', width: 300, height: 300,
          marginLeft: -150, marginTop: -150, borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(0,207,255,0.1), transparent)',
          animation: 'pulseBg 3s ease-in-out infinite',
        }} />
        <div style={{ position: 'absolute', top: '50%', left: '50%', width: 200, height: 200, marginLeft: -100, marginTop: -100, border: '1px solid rgba(0,207,255,0.08)', borderRadius: '50%', animation: 'pulseBg 4s ease-in-out infinite' }} />
        <div style={{ position: 'absolute', top: '50%', left: '50%', width: 120, height: 120, marginLeft: -60, marginTop: -60, border: '1px solid rgba(0,207,255,0.12)', borderRadius: '50%', animation: 'pulseBg 2s ease-in-out infinite' }} />
      </div>
    )
  }

  return (
    <Canvas
      camera={{ position: [0, 2, 8], fov: 50 }}
      gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      onCreated={(state) => {
        const cvs = state.gl.domElement
        cvs.addEventListener('webglcontextlost', (e) => { e.preventDefault(); setWebglFailed(true) }, false)
        cvs.addEventListener('webglcontextrestored', () => setWebglFailed(false), false)
      }}
      style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: Z.SCENE, pointerEvents: 'none' }}
    >
      <SceneContent />
    </Canvas>
  )
}
