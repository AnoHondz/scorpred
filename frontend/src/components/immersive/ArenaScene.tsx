import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { useEffect, useRef, useState } from 'react';
import { DoubleSide, MathUtils, type Group } from 'three';
import type { ArenaSport } from './SportsArena';

function Stripe({ x = 0, z = 0, w = .025, h = 5.5, color = '#b7ddd8' }: { x?: number; z?: number; w?: number; h?: number; color?: string }) {
  return <mesh rotation={[-Math.PI / 2, 0, 0]} position={[x, .035, z]}><planeGeometry args={[w, h]} /><meshBasicMaterial color={color} transparent opacity={.8} /></mesh>;
}
function Ring({ x = 0, z = 0, radius = .8, color = '#b7ddd8', start = 0, arc = Math.PI * 2 }: { x?: number; z?: number; radius?: number; color?: string; start?: number; arc?: number }) {
  return <mesh rotation={[-Math.PI / 2, 0, 0]} position={[x, .04, z]}><ringGeometry args={[radius - .018, radius, 48, 1, start, arc]} /><meshBasicMaterial color={color} side={DoubleSide} /></mesh>;
}
function Frame({ x = 0, z = 0, w = 10, h = 5.5 }: { x?: number; z?: number; w?: number; h?: number }) {
  return <><Stripe x={x - w / 2} z={z} h={h} /><Stripe x={x + w / 2} z={z} h={h} /><Stripe x={x} z={z - h / 2} w={w} h={.025} /><Stripe x={x} z={z + h / 2} w={w} h={.025} /></>;
}
function Goal({ x, basketball = false }: { x: number; basketball?: boolean }) {
  const accent = basketball ? '#ffb06a' : '#c5e7eb';
  return <group position={[x, 0, 0]}>
    <mesh position={[0, .65, 0]}><boxGeometry args={[.055, 1.3, basketball ? .06 : 1.7]} /><meshStandardMaterial color={accent} metalness={.65} roughness={.25} /></mesh>
    {basketball ? <><mesh position={[0, 1.35, 0]}><boxGeometry args={[.07, .65, 1.15]} /><meshPhysicalMaterial color="#77cce5" transparent opacity={.4} metalness={.1} roughness={.2} /></mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[x < 0 ? .32 : -.32, 1.1, 0]}><torusGeometry args={[.22, .025, 8, 32]} /><meshStandardMaterial color="#ff9254" emissive="#ff5926" emissiveIntensity={.15} /></mesh></>
      : <><mesh position={[0, .65, -.85]}><boxGeometry args={[.05, 1.3, .05]} /><meshStandardMaterial color={accent} /></mesh><mesh position={[0, .65, .85]}><boxGeometry args={[.05, 1.3, .05]} /><meshStandardMaterial color={accent} /></mesh></>}
  </group>;
}

function FootballField() {
  return <><mesh position={[0, .01, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[11, 6]} /><meshStandardMaterial color="#063c32" roughness={.85} /></mesh>
    <Frame />{Array.from({ length: 9 }, (_, i) => <Stripe key={i} x={-4 + i} />)}
    {Array.from({ length: 19 }, (_, i) => <group key={i}><Stripe x={-4.5 + i * .5} z={-.9} w={.025} h={.17} /><Stripe x={-4.5 + i * .5} z={.9} w={.025} h={.17} /></group>)}
    {[-5, 5].map(x => <group key={x} position={[x, 0, 0]}><mesh position={[0, .8, 0]}><boxGeometry args={[.055, 1.6, .055]} /><meshStandardMaterial color="#ffd58b" /></mesh><mesh position={[0, 1.6, 0]}><boxGeometry args={[.055, .05, 1.5]} /><meshStandardMaterial color="#ffd58b" /></mesh>{[-.75, .75].map(z => <mesh key={z} position={[0, 2.05, z]}><boxGeometry args={[.05, .9, .05]} /><meshStandardMaterial color="#ffd58b" /></mesh>)}</group>)}
  </>;
}

function BasketballCourt() {
  return <><mesh position={[0, .01, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[11, 6]} /><meshStandardMaterial color="#785339" roughness={.48} metalness={.08} /></mesh>
    {Array.from({ length: 15 }, (_, i) => <Stripe key={i} z={-2.8 + i * .4} w={10.8} h={.008} color="#9c7751" />)}
    <Frame /><Stripe /><Ring radius={.85} />
    {[-1, 1].map(sign => <group key={sign}><mesh rotation={[-Math.PI / 2, 0, 0]} position={[sign * 4.1, .02, 0]}><planeGeometry args={[1.8, 2.3]} /><meshStandardMaterial color="#0b3942" /></mesh><Frame x={sign * 4.1} w={1.8} h={2.3} /><Ring x={sign * 3.2} radius={.8} /><Ring x={sign * 4.7} radius={2.2} start={sign < 0 ? -Math.PI / 2 : Math.PI / 2} arc={Math.PI} /><Goal x={sign * 4.8} basketball /></group>)}
  </>;
}

function SoccerPitch() {
  return <><mesh position={[0, .01, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow><planeGeometry args={[11, 6]} /><meshStandardMaterial color="#07573e" roughness={.86} /></mesh>
    {Array.from({ length: 5 }, (_, i) => <mesh key={i} rotation={[-Math.PI / 2, 0, 0]} position={[-4.4 + i * 2.2, .015, 0]}><planeGeometry args={[1.1, 6]} /><meshStandardMaterial color="#0a6248" roughness={.9} /></mesh>)}
    <Frame /><Stripe /><Ring />{[-1, 1].map(sign => <group key={sign}><Frame x={sign * 4.2} w={1.6} h={3.3} /><Frame x={sign * 4.75} w={.5} h={1.7} /><Goal x={sign * 5.05} /></group>)}
  </>;
}

function Ball({ sport, onSelect }: { sport: ArenaSport; onSelect: () => void }) {
  const group = useRef<Group>(null);
  const [hovered, setHovered] = useState(false);
  useFrame(({ clock }, dt) => {
    if (!group.current) return;
    group.current.position.y = 1.15 + Math.sin(clock.elapsedTime * .8) * .1;
    group.current.rotation.y += Math.min(dt, .06) * .15;
    group.current.scale.setScalar(MathUtils.damp(group.current.scale.x, hovered ? 1.12 : 1, 6, Math.min(dt, .06)));
  });
  const material = <meshPhysicalMaterial color={sport === 'nba' ? '#e78635' : sport === 'nfl' ? '#512d21' : '#d2e3e6'} roughness={.35} metalness={.15} clearcoat={.45} />;
  return <group ref={group} position={[0, 1.15, 0]} onClick={event => { event.stopPropagation(); onSelect(); }} onPointerOver={() => setHovered(true)} onPointerOut={() => setHovered(false)}>
    <mesh castShadow scale={sport === 'nfl' ? [1.1, .62, .62] : [.72, .72, .72]} rotation={sport === 'nfl' ? [0, 0, -.25] : [0, 0, 0]}><sphereGeometry args={[1, 32, 24]} />{material}</mesh>
    {sport === 'nba' && [0, 1, 2].map(i => <mesh key={i} rotation={[i === 0 ? Math.PI / 2 : 0, i === 1 ? Math.PI / 2 : 0, i === 2 ? Math.PI / 2 : 0]}><torusGeometry args={[.724, .012, 6, 64]} /><meshStandardMaterial color="#261a13" /></mesh>)}
    {sport === 'soccer' && <mesh rotation={[.25, .5, 0]}><icosahedronGeometry args={[.733, 1]} /><meshStandardMaterial color="#071c22" wireframe wireframeLinewidth={2} /></mesh>}
    {sport === 'nfl' && <group position={[0, .57, .15]} rotation={[0, 0, -.25]}>{[-2, -1, 0, 1, 2].map(i => <mesh key={i} position={[i * .17, 0, 0]}><boxGeometry args={[.035, .04, .25]} /><meshStandardMaterial color="#eee9d7" /></mesh>)}</group>}
  </group>;
}

function World({ sport, active, side, onSelect }: { sport: ArenaSport; active: boolean; side: 'home' | 'away'; onSelect: () => void }) {
  const group = useRef<Group>(null);
  const { invalidate } = useThree();
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(invalidate, 1000 / 30);
    return () => clearInterval(timer);
  }, [active, invalidate]);
  useFrame(({ pointer }, dt) => {
    if (!group.current) return;
    group.current.rotation.y = MathUtils.damp(group.current.rotation.y, (side === 'home' ? -.12 : .12) + pointer.x * .13, 4, Math.min(dt, .06));
    group.current.rotation.x = MathUtils.damp(group.current.rotation.x, pointer.y * .035, 4, Math.min(dt, .06));
  });
  return <>
    <ambientLight intensity={.65} /><hemisphereLight args={['#80c8ff', '#07101a', 1.3]} />
    <directionalLight position={[3, 9, 3]} intensity={3} color="#dbf5ff" castShadow shadow-mapSize={[512, 512]} />
    <pointLight position={[-5, 4, 1]} intensity={45} color="#00e8bd" distance={18} />
    <pointLight position={[5, 3, -3]} intensity={50} color="#347cff" distance={18} />
    <group ref={group}>
      <mesh position={[0, -.2, 0]} receiveShadow><boxGeometry args={[11.5, .4, 6.5]} /><meshStandardMaterial color="#0d202b" metalness={.65} roughness={.35} /></mesh>
      <mesh position={[0, -.42, 0]}><boxGeometry args={[11.35, .06, 6.35]} /><meshStandardMaterial color="#0ad8b1" emissive="#00c49a" emissiveIntensity={2} /></mesh>
      {[-1, 1].map(sign => <group key={sign}>{[0, 1, 2].map(row => <group key={row}><mesh position={[0, row * .25, sign * (3.6 + row * .35)]}><boxGeometry args={[12, .3, .45]} /><meshStandardMaterial color="#172d3a" metalness={.45} roughness={.4} /></mesh><mesh position={[0, row * .25 + .17, sign * (3.6 + row * .35)]}><boxGeometry args={[11.7, .025, .04]} /><meshStandardMaterial color={sign === 1 ? '#16bfa8' : '#1685ce'} emissive={sign === 1 ? '#16bfa8' : '#1685ce'} emissiveIntensity={1.6} /></mesh></group>)}</group>)}
      {sport === 'nba' ? <BasketballCourt /> : sport === 'nfl' ? <FootballField /> : <SoccerPitch />}
      <Ball sport={sport} onSelect={onSelect} />
    </group>
  </>;
}

export default function ArenaScene({ sport, active, side, onSelect, dpr }: {
  sport: ArenaSport; active: boolean; side: 'home' | 'away'; onSelect: () => void; dpr: number;
}) {
  return <Canvas className="arena-canvas" camera={{ position: [10, 10.5, 13], fov: 35 }} dpr={[1, dpr]} frameloop="demand" shadows gl={{ antialias: false, alpha: true, powerPreference: 'low-power' }} onCreated={({ gl }) => {
    gl.domElement.dataset.renderer = 'webgl'; gl.domElement.dataset.maxDpr = String(dpr);
  }}>
    <World sport={sport} active={active} side={side} onSelect={onSelect} />
  </Canvas>;
}
