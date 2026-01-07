'use client';

import { useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

const POINTS = 600;

function ParticleField() {
  const positions = useMemo(() => {
    const arr = new Float32Array(POINTS * 3);
    for (let i = 0; i < POINTS; i += 1) {
      const radius = 0.35 + Math.random() * 0.65;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.sin(phi) * Math.sin(theta);
      const z = radius * Math.cos(phi);
      arr[i * 3] = x;
      arr[i * 3 + 1] = y;
      arr[i * 3 + 2] = z;
    }
    return arr;
  }, []);

  const ref = useRef<THREE.Points>(null);
  useFrame((_state, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * 0.08;
      ref.current.rotation.x += delta * 0.025;
    }
  });

  return (
    <points ref={ref} scale={2.4}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={POINTS} array={positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial
        size={0.015}
        color={new THREE.Color('#7dd3fc')}
        sizeAttenuation
        transparent
        opacity={0.8}
      />
    </points>
  );
}

function Ribbon() {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_state, delta) => {
    if (ref.current) {
      ref.current.rotation.y -= delta * 0.12;
    }
  });

  return (
    <mesh ref={ref} scale={[1.6, 1.6, 1.6]}>
      <torusGeometry args={[0.6, 0.07, 64, 256]} />
      <meshStandardMaterial
        color="#fbbf24"
        metalness={0.4}
        roughness={0.3}
        emissive="#fbbf24"
        emissiveIntensity={0.5}
      />
    </mesh>
  );
}

export default function DataAurora() {
  return (
    <div className="h-64 w-full overflow-hidden rounded-3xl border border-white/5 bg-black/40">
      <Canvas camera={{ position: [0, 0, 3.5], fov: 50 }}>
        <ambientLight intensity={0.7} />
        <directionalLight position={[3, 3, 2]} intensity={1.1} />
        <color attach="background" args={[0, 0, 0]} />
        <ParticleField />
        <Ribbon />
        <OrbitControls enablePan={false} enableZoom={false} autoRotate autoRotateSpeed={0.6} />
      </Canvas>
    </div>
  );
}
