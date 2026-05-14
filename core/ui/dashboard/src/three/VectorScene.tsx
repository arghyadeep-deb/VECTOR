import { useRef, useMemo, useState, useEffect } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { Z } from '../lib/zIndex'

function CoreSphere() {
  const ref = useRef<THREE.Mesh>(null!)
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    ref.current.rotation.x = Math.sin(t * 0.15) * 0.1
    ref.current.rotation.y = t * 0.08
    ref.current.scale.setScalar(1 + Math.sin(t * 0.6) * 0.02)
  })
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[0.8, 1]} />
      <meshPhysicalMaterial color="#00CFFF" roughness={0.05} metalness={0.9} transparent opacity={0.6} emissive="#002244" emissiveIntensity={0.5} />
    </mesh>
  )
}

function CoreWireframe() {
  const ref = useRef<THREE.Mesh>(null!)
  useFrame(({ clock }) => { ref.current.rotation.x = Math.sin(clock.getElapsedTime() * 0.12) * 0.15; ref.current.rotation.y = -clock.getElapsedTime() * 0.06 })
  return (
    <mesh ref={ref}>
      <icosahedronGeometry args={[1.1, 1]} />
      <meshBasicMaterial color="#00CFFF" wireframe transparent opacity={0.15} />
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

function HolographicRing({ radius = 2.5, speed = 0.4, color = '#00CFFF', tilt = 0 }: { radius?: number; speed?: number; color?: string; tilt?: number }) {
  const ref = useRef<THREE.Group>(null!)
  useFrame(({ clock }) => { ref.current.rotation.y = clock.getElapsedTime() * speed })
  return (
    <group ref={ref} rotation={[tilt, 0, 0]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[radius, 0.02, 8, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.3} />
      </mesh>
    </group>
  )
}

function ParticleField() {
  const ref = useRef<THREE.Points>(null!)
  const count = 200
  const positions = useMemo(() => { const arr = new Float32Array(count * 3); for (let i = 0; i < count * 3; i++) arr[i] = (Math.random() - 0.5) * 30; return arr }, [])
  useFrame(({ clock }) => { ref.current.rotation.y = clock.getElapsedTime() * 0.02 })
  return (
    <points ref={ref}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry>
      <pointsMaterial size={0.05} color="#00CFFF" transparent opacity={0.4} sizeAttenuation />
    </points>
  )
}

function SceneContent() {
  return (
    <>
      <ambientLight intensity={0.1} />
      <pointLight position={[5, 5, 5]} intensity={0.8} color="#00CFFF" />
      <GlowSphere /><CoreSphere /><CoreWireframe />
      <HolographicRing radius={2.2} speed={0.5} color="#00CFFF" />
      <HolographicRing radius={3.5} speed={-0.3} color="#00CFFF" tilt={0.15} />
      <HolographicRing radius={5.0} speed={0.2} color="#00CFFF" tilt={-0.1} />
      <ParticleField />
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
        background: '#020B18',
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
      style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: '#020B18', zIndex: Z.SCENE }}
    >
      <SceneContent />
    </Canvas>
  )
}
