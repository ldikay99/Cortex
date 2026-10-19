import * as THREE from 'three';
import { mulberry32 } from './rand.js';
import { pointsMaterial, pointsGeometry } from './materials.js';

const CORE_R = 1.7;
const THREAD_SEG = 40;
const MAX_THREADS = 48;
const MAX_PULSES = 96;
const MOTES = 220;

export function createNest(scene, center = new THREE.Vector3()) {
  const rng = mulberry32(0x4e57);
  const group = new THREE.Group();
  group.position.copy(center);
  scene.add(group);
  const lineMat = () => new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });

  const rings = [];
  const ringDefs = [
    { r: CORE_R, tilt: [0, 0, 0], speed: 0.35, color: [0.45, 0.95, 1.0], k: 0.75 },
    { r: CORE_R * 0.98, tilt: [Math.PI / 2, 0, 0], speed: -0.28, color: [0.55, 0.85, 1.0], k: 0.6 },
    { r: CORE_R * 0.96, tilt: [Math.PI / 3, Math.PI / 4, 0], speed: 0.22, color: [0.75, 0.7, 1.0], k: 0.55 },
    { r: CORE_R * 0.94, tilt: [-Math.PI / 3, Math.PI / 5, Math.PI / 2], speed: -0.4, color: [0.95, 0.8, 1.0], k: 0.45 },
    { r: CORE_R * 0.62, tilt: [0.4, 0.2, 0.9], speed: 0.9, color: [1.0, 0.95, 0.85], k: 0.7 },
    { r: CORE_R * 0.45, tilt: [1.2, 0.6, 0.1], speed: -1.2, color: [1.0, 0.92, 0.8], k: 0.8 },
  ];
  for (const d of ringDefs) {
    const pos = [], col = [];
    const N = 96;
    for (let i = 0; i < N; i++) {
      const a0 = (i / N) * Math.PI * 2, a1 = ((i + 1) / N) * Math.PI * 2;
      pos.push(Math.cos(a0) * d.r, 0, Math.sin(a0) * d.r, Math.cos(a1) * d.r, 0, Math.sin(a1) * d.r);
      const b0 = 0.35 + 0.65 * Math.pow(0.5 + 0.5 * Math.cos(a0), 3), b1 = 0.35 + 0.65 * Math.pow(0.5 + 0.5 * Math.cos(a1), 3);
      col.push(...d.color.map((c) => c * d.k * b0), ...d.color.map((c) => c * d.k * b1));
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    const pivot = new THREE.Group();
    pivot.rotation.set(...d.tilt);
    const mesh = new THREE.LineSegments(g, lineMat());
    pivot.add(mesh);
    group.add(pivot);
    rings.push({ mesh, speed: d.speed });
  }

  const glowTex = (() => {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 128;
    const ctx = cv.getContext('2d');
    const gr = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, 'rgba(210,250,255,0.9)');
    gr.addColorStop(0.18, 'rgba(120,220,255,0.35)');
    gr.addColorStop(0.5, 'rgba(80,150,255,0.08)');
    gr.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = gr;
    ctx.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(cv);
  })();
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  glow.scale.setScalar(CORE_R * 3.4);
  group.add(glow);

  const moteGeo = pointsGeometry(MOTES, { color: [0.7, 0.95, 1.0] });
  const motes = Array.from({ length: MOTES }, () => ({
    r: CORE_R * (1.15 + rng() * 1.6),
    a: rng() * Math.PI * 2,
    s: (0.15 + rng() * 0.4) * (rng() < 0.5 ? 1 : -1),
    axis: new THREE.Vector3(rng() - 0.5, rng() - 0.5, rng() - 0.5).normalize(),
  }));
  {
    const sz = moteGeo.attributes.aSize.array, al = moteGeo.attributes.aAlpha.array;
    for (let i = 0; i < MOTES; i++) (sz[i] = 0.03 + rng() * 0.04), (al[i] = 0.3 + rng() * 0.45);
  }
  const moteMat = pointsMaterial({ fog: 0.0009, heatSize: 0, maxPx: 10 });
  const motePts = new THREE.Points(moteGeo, moteMat);
  motePts.frustumCulled = false;
  group.add(motePts);

  const tPos = new Float32Array(MAX_THREADS * THREAD_SEG * 6);
  const tCol = new Float32Array(MAX_THREADS * THREAD_SEG * 6);
  const tBase = new Float32Array(MAX_THREADS * THREAD_SEG * 6);
  const tGeo = new THREE.BufferGeometry();
  tGeo.setAttribute('position', new THREE.BufferAttribute(tPos, 3));
  tGeo.setAttribute('color', new THREE.BufferAttribute(tCol, 3));
  tGeo.setDrawRange(0, 0);
  const threadLines = new THREE.LineSegments(tGeo, lineMat());
  threadLines.frustumCulled = false;
  scene.add(threadLines);
  const threads = [];
  const pulseGeo = pointsGeometry(MAX_PULSES, { size: 0.16, alpha: 0 });
  const pulseMat = pointsMaterial({ fog: 0.0007, heatSize: 0, maxPx: 40 });
  const pulsePts = new THREE.Points(pulseGeo, pulseMat);
  pulsePts.frustumCulled = false;
  scene.add(pulsePts);
  const pulses = [];
  let beat = 0;
  const tmp = new THREE.Vector3();

  function addThread(region, to, radius, color) {
    if (threads[region] || threads.filter(Boolean).length >= MAX_THREADS) return;
    const k = threads.filter(Boolean).length;
    const dir = tmp.copy(to).sub(center).normalize();
    const start = center.clone().addScaledVector(dir, CORE_R * 1.1);
    const end = to.clone().addScaledVector(dir, -radius * 0.55);
    const side = new THREE.Vector3(rng() - 0.5, rng() - 0.5, rng() - 0.5).cross(dir).normalize();
    const ctrl = start.clone().lerp(end, 0.5).addScaledVector(side, start.distanceTo(end) * 0.12);
    const pts = [];
    for (let i = 0; i <= THREAD_SEG; i++) {
      const t = i / THREAD_SEG, u = 1 - t;
      pts.push(new THREE.Vector3(
        u * u * start.x + 2 * u * t * ctrl.x + t * t * end.x,
        u * u * start.y + 2 * u * t * ctrl.y + t * t * end.y,
        u * u * start.z + 2 * u * t * ctrl.z + t * t * end.z
      ));
    }
    for (let i = 0; i < THREAD_SEG; i++) {
      const o = (k * THREAD_SEG + i) * 6;
      const a = pts[i], b = pts[i + 1];
      tPos.set([a.x, a.y, a.z, b.x, b.y, b.z], o);
      for (const [off, t] of [[0, i / THREAD_SEG], [3, (i + 1) / THREAD_SEG]]) {
        const fade = 0.07 + 0.06 * Math.abs(t - 0.5) * 2;
        for (let q = 0; q < 3; q++) tBase[o + off + q] = ([0.5, 0.95, 1.0][q] * (1 - t) + color[q] * t) * fade;
      }
    }
    threads[region] = { pts, slot: k, color };
    tGeo.setDrawRange(0, (k + 1) * THREAD_SEG * 2);
    tGeo.attributes.position.needsUpdate = true;
  }

  return {
    addThread,
    pulse(region) {
      beat = 1;
      const th = threads[region];
      if (!th || pulses.length >= MAX_PULSES) return;
      pulses.push({ th, t: 0, speed: 0.55 + rng() * 0.3 });
    },
    update(dt, time) {
      beat *= Math.exp(-dt * 3.5);
      const heart = 1 + 0.06 * Math.pow(Math.max(0, Math.sin(time * 2.2)), 8) + beat * 0.12;
      for (const r of rings) r.mesh.rotation.y += dt * r.speed;
      group.scale.setScalar(heart);
      glow.material.opacity = 0.55 + beat * 0.35 + 0.08 * Math.sin(time * 2.2);

      const mp = moteGeo.attributes.position.array;
      motes.forEach((m, i) => {
        m.a += dt * m.s;
        tmp.set(Math.cos(m.a) * m.r, 0, Math.sin(m.a) * m.r).applyAxisAngle(m.axis, 0.9);
        mp[i * 3] = tmp.x, mp[i * 3 + 1] = tmp.y, mp[i * 3 + 2] = tmp.z;
      });
      moteGeo.attributes.position.needsUpdate = true;

      tCol.set(tBase);
      const pp = pulseGeo.attributes.position.array, pa = pulseGeo.attributes.aAlpha.array, pc = pulseGeo.attributes.color.array;
      let w = 0;
      for (const p of pulses) {
        p.t += dt * p.speed;
        if (p.t >= 1) continue;
        const f = p.t * THREAD_SEG;
        const i = Math.min(THREAD_SEG - 1, Math.floor(f));
        tmp.copy(p.th.pts[i]).lerp(p.th.pts[i + 1], f - i);
        pp[w * 3] = tmp.x, pp[w * 3 + 1] = tmp.y, pp[w * 3 + 2] = tmp.z;
        pa[w] = 0.85 * Math.sin(Math.PI * p.t) + 0.15;
        pc.set([0.8 + p.th.color[0] * 0.2, 0.95, 1.0], w * 3);
        for (let j = Math.max(0, i - 4); j <= Math.min(THREAD_SEG - 1, i + 1); j++) {
          const o = (p.th.slot * THREAD_SEG + j) * 6;
          const k = 0.35 * (1 - Math.abs(j - i) / 5);
          for (let q = 0; q < 6; q++) tCol[o + q] += k;
        }
        pulses[w++] = p;
      }
      pulses.length = w;
      pulseGeo.setDrawRange(0, w);
      pulseGeo.attributes.position.needsUpdate = pulseGeo.attributes.aAlpha.needsUpdate = pulseGeo.attributes.color.needsUpdate = true;
      tGeo.attributes.color.needsUpdate = true;
    },
    materials: [moteMat, pulseMat],
  };
}
