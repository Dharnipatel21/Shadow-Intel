'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export type GraphNode = {
  id: string;
  label: string;
  type: string;
  priority?: number;
  community?: number;
};
export type GraphEdge = { source: string; target: string; type?: string; confidence?: number };
type Theme = 'dark' | 'light';

const TYPE_COLOR: Record<string, string> = {
  Person: '#d9a441',
  Phone: '#8b6fd1',
  BankAccount: '#c9793f',
  Organization: '#5b8fd1',
  Location: '#3fae94',
};
const FALLBACK_COLOR = '#9aa5b8';
const THREAD_ACCENT = '#d1483f';

function hash01(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i++) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxWidth: number, lineHeight: number, maxLines: number) {
  const words = text.split(' ');
  let line = '';
  let lines = 0;
  for (let i = 0; i < words.length; i++) {
    const test = line ? line + ' ' + words[i] : words[i];
    if (ctx.measureText(test).width > maxWidth && line) {
      ctx.fillText(line, x, y + lines * lineHeight);
      line = words[i];
      lines++;
      if (lines >= maxLines - 1) {
        const rest = words.slice(i).join(' ');
        const truncated = ctx.measureText(rest).width > maxWidth ? rest.slice(0, 18) + '…' : rest;
        ctx.fillText(truncated, x, y + lines * lineHeight);
        return;
      }
    } else {
      line = test;
    }
  }
  ctx.fillText(line, x, y + lines * lineHeight);
}

function buildCardTexture(node: GraphNode, theme: Theme, highlighted: boolean): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 320;
  const ctx = canvas.getContext('2d')!;
  const isDark = theme === 'dark';
  const bg = isDark ? '#151926' : '#fffdf7';
  const border = highlighted ? THREAD_ACCENT : isDark ? '#2c3247' : '#ddd2b6';
  const text = isDark ? '#eef1f6' : '#221f18';
  const dim = isDark ? '#8891a5' : '#8a8064';
  const typeColor = TYPE_COLOR[node.type] || FALLBACK_COLOR;

  roundRect(ctx, 8, 8, canvas.width - 16, canvas.height - 16, 24);
  ctx.fillStyle = bg;
  ctx.fill();
  ctx.lineWidth = highlighted ? 8 : 4;
  ctx.strokeStyle = border;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(44, 44, 11, 0, Math.PI * 2);
  ctx.fillStyle = typeColor;
  ctx.fill();

  ctx.font = '600 24px "IBM Plex Mono", monospace';
  ctx.fillStyle = typeColor;
  ctx.fillText(node.type.toUpperCase(), 68, 52);

  ctx.font = '700 38px Inter, sans-serif';
  ctx.fillStyle = text;
  wrapText(ctx, node.label, 40, 128, canvas.width - 80, 44, 3);

  if (typeof node.priority === 'number') {
    ctx.font = '500 22px "IBM Plex Mono", monospace';
    ctx.fillStyle = dim;
    ctx.fillText('PRIORITY ' + Math.round(node.priority), 40, canvas.height - 32);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return tex;
}

type LaidOutNode = GraphNode & { position: [number, number, number] };

function layoutNodes(nodes: GraphNode[]): LaidOutNode[] {
  const communities = Array.from(new Set(nodes.map((n) => n.community ?? 0)));
  const angleStep = (Math.PI * 2) / Math.max(communities.length, 1);
  const clusterRadius = communities.length > 1 ? 4.6 + communities.length * 0.5 : 0;
  return nodes.map((n) => {
    const ci = communities.indexOf(n.community ?? 0);
    const clusterAngle = ci * angleStep;
    const cx = Math.cos(clusterAngle) * clusterRadius;
    const cz = Math.sin(clusterAngle) * clusterRadius;
    const r = 1.3 + hash01(n.id) * 3.1;
    const a = hash01(n.id + ':a') * Math.PI * 2;
    const y = (hash01(n.id + ':y') - 0.5) * 4.2;
    return { ...n, position: [cx + Math.cos(a) * r, y, cz + Math.sin(a) * r] as [number, number, number] };
  });
}

function edgeCurve(a: [number, number, number], b: [number, number, number]) {
  const start = new THREE.Vector3(...a);
  const end = new THREE.Vector3(...b);
  const mid = start.clone().lerp(end, 0.5);
  const dist = start.distanceTo(end);
  mid.y -= Math.min(dist * 0.16, 1.3);
  return new THREE.QuadraticBezierCurve3(start, mid, end);
}

function Thread({ a, b, accent, theme }: { a: [number, number, number]; b: [number, number, number]; accent: boolean; theme: Theme }) {
  const geometry = useMemo(() => {
    const curve = edgeCurve(a, b);
    return new THREE.TubeGeometry(curve, 18, accent ? 0.017 : 0.009, 5, false);
  }, [a, b, accent]);
  const color = accent ? THREAD_ACCENT : theme === 'dark' ? '#394058' : '#cdc2a6';
  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial color={color} transparent opacity={accent ? 0.95 : 0.55} toneMapped={false} />
    </mesh>
  );
}

function Card({
  node,
  highlighted,
  interactive,
  compact,
  theme,
  onSelect,
}: {
  node: LaidOutNode;
  highlighted: boolean;
  interactive: boolean;
  compact: boolean;
  theme: Theme;
  onSelect?: (id: string) => void;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const { camera } = useThree();
  const texture = useMemo(() => buildCardTexture(node, theme, highlighted), [node.label, node.type, node.priority, theme, highlighted]);
  useFrame(() => {
    if (ref.current) ref.current.quaternion.copy(camera.quaternion);
  });
  const w = compact ? 1.05 : 1.55;
  const h = w * 0.625;
  return (
    <group position={node.position}>
      <mesh
        ref={ref}
        onClick={interactive ? (e) => { e.stopPropagation(); onSelect?.(node.id); } : undefined}
        onPointerOver={interactive ? () => { document.body.style.cursor = 'pointer'; } : undefined}
        onPointerOut={interactive ? () => { document.body.style.cursor = 'auto'; } : undefined}
      >
        <planeGeometry args={[w, h]} />
        <meshBasicMaterial map={texture} transparent toneMapped={false} />
      </mesh>
    </group>
  );
}

function Controls({ enabled }: { enabled: boolean }) {
  const { camera, gl } = useThree();
  const controlsRef = useRef<OrbitControls | null>(null);
  useEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 6;
    controls.maxDistance = 24;
    controlsRef.current = controls;
    return () => controls.dispose();
  }, [camera, gl]);
  useEffect(() => {
    if (controlsRef.current) controlsRef.current.enabled = enabled;
  }, [enabled]);
  useFrame(() => controlsRef.current?.update());
  return null;
}

function Scene({
  layout,
  edges,
  theme,
  focusId,
  interactive,
  compact,
  onSelect,
  autoRotate,
}: {
  layout: LaidOutNode[];
  edges: GraphEdge[];
  theme: Theme;
  focusId?: string;
  interactive: boolean;
  compact: boolean;
  onSelect?: (id: string) => void;
  autoRotate: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const byId = useMemo(() => Object.fromEntries(layout.map((n) => [n.id, n])), [layout]);
  useFrame((_, delta) => {
    if (group.current && autoRotate) group.current.rotation.y += delta * 0.07;
  });
  return (
    <group ref={group}>
      {edges.map((e, i) => {
        const a = byId[e.source];
        const b = byId[e.target];
        if (!a || !b) return null;
        const accent = a.id === focusId || b.id === focusId || (a.priority ?? 0) >= 70 || (b.priority ?? 0) >= 70;
        return <Thread key={i} a={a.position} b={b.position} accent={accent} theme={theme} />;
      })}
      {layout.map((n) => (
        <Card key={n.id} node={n} highlighted={n.id === focusId} interactive={interactive} compact={compact} theme={theme} onSelect={onSelect} />
      ))}
    </group>
  );
}

export default function NetworkGraph3D({
  nodes,
  edges,
  focusId,
  theme = 'dark',
  interactive = false,
  onSelectNode,
  height = 320,
  maxNodes = 34,
  caption,
  legend = true,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  focusId?: string;
  theme?: Theme;
  interactive?: boolean;
  onSelectNode?: (id: string) => void;
  height?: number | string;
  maxNodes?: number;
  caption?: string;
  legend?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(mq.matches);
    const listener = () => setReducedMotion(mq.matches);
    mq.addEventListener('change', listener);
    return () => mq.removeEventListener('change', listener);
  }, []);

  const limited = useMemo(() => {
    if (nodes.length <= maxNodes) return nodes;
    const prioritized = [...nodes].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
    const keep = new Set(prioritized.slice(0, maxNodes).map((n) => n.id));
    if (focusId) keep.add(focusId);
    return nodes.filter((n) => keep.has(n.id));
  }, [nodes, maxNodes, focusId]);
  const idSet = useMemo(() => new Set(limited.map((n) => n.id)), [limited]);
  const layout = useMemo(() => layoutNodes(limited), [limited]);
  const visibleEdges = useMemo(() => edges.filter((e) => idSet.has(e.source) && idSet.has(e.target)), [edges, idSet]);

  const activeTypes = useMemo(() => Array.from(new Set(limited.map((n) => n.type))), [limited]);

  return (
    <div
      className="graph3d"
      style={{ height }}
      onPointerDown={() => interactive && setDragging(true)}
      onPointerUp={() => setDragging(false)}
      onPointerLeave={() => setDragging(false)}
    >
      <Canvas camera={{ position: [0, 2.4, 12.5], fov: 42 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }}>
        <ambientLight intensity={0.85} />
        <pointLight position={[8, 10, 9]} intensity={70} color={theme === 'light' ? '#ffffff' : '#dfe9ff'} />
        <pointLight position={[-9, -5, -8]} intensity={26} color={THREAD_ACCENT} />
        <Scene
          layout={layout}
          edges={visibleEdges}
          theme={theme}
          focusId={focusId}
          interactive={interactive}
          compact={!interactive}
          onSelect={onSelectNode}
          autoRotate={!dragging && !reducedMotion}
        />
        {interactive && <Controls enabled={!reducedMotion || dragging} />}
      </Canvas>
      {legend && (
        <div className="graph3d-legend">
          {activeTypes.map((t) => (
            <span className="item" key={t}>
              <span className="dot" style={{ background: TYPE_COLOR[t] || FALLBACK_COLOR }} />
              {t}
            </span>
          ))}
        </div>
      )}
      {caption && <div className="graph3d-caption">{caption}</div>}
      {interactive && <div className="graph3d-hint">Drag to rotate · click a card to select</div>}
    </div>
  );
}