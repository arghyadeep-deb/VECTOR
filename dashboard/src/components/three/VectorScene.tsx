'use client';

import { useRef, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

function CoreSphere() {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    ref.current.rotation.y = Math.sin(t * 0.3) * 0.15;
    ref.current.scale.x = 1 + Math.sin(t) * 0.04;
    ref.current.scale.y = 1 + Math.cos(t * 1.3) * 0.04;
    ref.current.scale.z = 1 + Math.sin(t * 0.7) * 0.04;
  });

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[1, 64, 64]} />
      <meshPhysicalMaterial
        color="#00ddff"
        roughness={0.05}
        metalness={0.95}
        transparent
        opacity={0.85}
        emissive="#003366"
        emissiveIntensity={0.3}
      />
    </mesh>
  );
}

function CoreGlow() {
  return (
    <mesh>
      <sphereGeometry args={[1.3, 32, 32]} />
      <meshBasicMaterial color="#00ddff" transparent opacity={0.06} />
    </mesh>
  );
}

function HoloRing({ radius = 3, speed = 1, color = '#00ffaa', tilt = 0 }: { radius?: number; speed?: number; color?: string; tilt?: number }) {
  const ref = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    ref.current.rotation.y = clock.getElapsedTime() * 0.3 * speed;
  });

  const curvePoints = Array.from({ length: 80 }, (_, i) => {
    const a = (i / 80) * Math.PI * 2;
    return new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius);
  });
  const curve = new THREE.CatmullRomCurve3(curvePoints);

  return (
    <group ref={ref} rotation={[tilt, 0, 0]}>
      <mesh>
        <tubeGeometry args={[curve, 80, 0.02, 8, false]} />
        <meshBasicMaterial color={color} transparent opacity={0.35} />
      </mesh>
      <mesh>
        <tubeGeometry args={[curve, 80, 0.005, 8, false]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.5} />
      </mesh>
    </group>
  );
}

function DataNode({ position, color = '#00aaff' }: { position: [number, number, number]; color?: string }) {
  const ref = useRef<THREE.Mesh>(null!);
  const startY = position[1];
  const [hovered, setHovered] = useState(false);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    ref.current.position.y = startY + Math.sin(t * 1.5 + position[0]) * 0.2;
    ref.current.rotation.x = t * 0.5;
    ref.current.rotation.y = t * 0.3;
  });

  return (
    <mesh
      ref={ref}
      position={position}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
    >
      <octahedronGeometry args={[0.16]} />
      <meshStandardMaterial
        color={color}
        emissive={hovered ? '#ff00ff' : color}
        emissiveIntensity={hovered ? 0.8 : 0.3}
        metalness={0.9}
        roughness={0.1}
      />
    </mesh>
  );
}

function ParticleField() {
  const ref = useRef<THREE.Points>(null!);
  const count = 600;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count * 3; i++) positions[i] = (Math.random() - 0.5) * 35;

  useFrame(({ clock }) => {
    ref.current.rotation.y = clock.getElapsedTime() * 0.02;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.04} color="#4488ff" transparent opacity={0.35} sizeAttenuation />
    </points>
  );
}

function ConnectionLines() {
  const positions = [
    [-3, 2, 0], [3, -2, 1], [0, 3, -2], [-2, -3, 2],
    [2.5, 1, -2.5], [-2.5, -1, -2], [1.5, -2.5, 2.5], [0, -3.5, -1]
  ];

  const verts: number[] = [];
  for (let i = 0; i < positions.length; i++) {
    for (let j = i + 1; j < positions.length; j++) {
      if (Math.random() > 0.35) continue;
      verts.push(...positions[i], ...positions[j]);
    }
  }

  return (
    <lineSegments>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={verts.length / 3}
          array={new Float32Array(verts)}
          itemSize={3}
        />
      </bufferGeometry>
      <lineBasicMaterial color="#00ffff" transparent opacity={0.06} />
    </lineSegments>
  );
}

function SceneContent() {
  return (
    <>
      <ambientLight intensity={0.12} />
      <pointLight position={[5, 5, 5]} intensity={1.2} color="#00ddff" />
      <pointLight position={[-5, -3, -5]} intensity={0.4} color="#ff44ff" />
      <pointLight position={[0, 8, 0]} intensity={0.2} color="#4488ff" />

      <CoreGlow />
      <CoreSphere />
      <HoloRing radius={2.5} speed={0.8} color="#00ffaa" />
      <HoloRing radius={3.8} speed={-0.5} color="#ff8800" tilt={0.15} />
      <HoloRing radius={5.0} speed={0.4} color="#aa44ff" tilt={-0.12} />
      <HoloRing radius={6.5} speed={-0.3} color="#00ddff" tilt={0.08} />

      <DataNode position={[-3, 2, 0]} color="#00ffaa" />
      <DataNode position={[3, -2, 1]} color="#ffaa00" />
      <DataNode position={[0, 3, -2]} color="#aa44ff" />
      <DataNode position={[-2, -3, 2]} color="#00ddff" />
      <DataNode position={[2.5, 1, -2.5]} color="#ff44aa" />
      <DataNode position={[-2.5, -1, -2]} color="#ff6666" />
      <DataNode position={[1.5, -2.5, 2.5]} color="#ffaa44" />
      <DataNode position={[0, -3.5, -1]} color="#44ffaa" />

      <ConnectionLines />
      <ParticleField />

      <OrbitControls
        enablePan
        enableZoom
        enableRotate
        autoRotate
        autoRotateSpeed={0.5}
        minDistance={3}
        maxDistance={20}
      />
    </>
  );
}

export default function Scene() {
  return (
    <Canvas
      camera={{ position: [0, 0, 8], fov: 60 }}
      gl={{ antialias: true, alpha: true }}
      style={{ background: '#000000' }}
    >
      <SceneContent />
    </Canvas>
  );
}