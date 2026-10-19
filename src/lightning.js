import * as THREE from 'three';
import { mulberry32 } from './rand.js';
import { pointsMaterial, pointsGeometry } from './materials.js';

const MAX_BOLTS = 24;
const SEGS = 150;
const MAIN_STRANDS = 3;

export function createLightning(scene, { fog = true, flashSize = 0.5, maxFlashPx = 90 } = {}) {
  const rng = mulberry32(0xb017);
  const posA = new Float32Array(MAX_BOLTS * SEGS * 6);
  const colA = new Float32Array(MAX_BOLTS * SEGS * 6);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(posA, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colA, 3));
  const mesh = new THREE.LineSegments(
    geo,
    new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog })
  );
  mesh.frustumCulled = false;
  scene.add(mesh);

  const flashGeo = pointsGeometry(MAX_BOLTS * 2, { size: flashSize, alpha: 0 });
  const flashMat = pointsMaterial({ fog: fog ? 0.0006 : 0, heatSize: 0, maxPx: maxFlashPx });
  const flashes = new THREE.Points(flashGeo, flashMat);
  flashes.frustumCulled = false;
  scene.add(flashes);

  const bolts = Array.from({ length: MAX_BOLTS }, () => ({
    life: 0, dur: 1, used: 0, weight: new Float32Array(SEGS), color: [1, 1, 1], power: 1, flick: 1, next: 0,
  }));
  const dir = new THREE.Vector3();
  const side = new THREE.Vector3();

  function jagged(a, b, depth, rough) {
    let pts = [a.clone(), b.clone()];
    dir.subVectors(b, a);
    let amp = dir.length() * rough;
    dir.normalize();
    for (let d = 0; d < depth; d++) {
      const next = [pts[0]];
      for (let i = 0; i < pts.length - 1; i++) {
        side.set(rng() - 0.5, rng() - 0.5, rng() - 0.5);
        side.addScaledVector(dir, -side.dot(dir)).normalize();
        const mid = pts[i].clone().lerp(pts[i + 1], 0.5).addScaledVector(side, (rng() - 0.5) * 2 * amp);
        next.push(mid, pts[i + 1]);
      }
      pts = next;
      amp *= 0.55;
    }
    return pts;
  }

  function strike(a, b, color = [0.8, 0.88, 1], power = 1) {
    let bolt = bolts.find((x) => x.life <= 0);
    if (!bolt) bolt = bolts.reduce((p, q) => (q.life < p.life ? q : p));
    const k = bolts.indexOf(bolt);
    const main = jagged(a, b, 5, 0.17);
    const len = a.distanceTo(b);
    const paths = [];
    for (let s = 0; s < MAIN_STRANDS; s++) {
      const j = s === 0 ? 0 : 0.035;
      paths.push([main.map((p, i) => (i === 0 || i === main.length - 1 ? p : p.clone().add(side.set(rng() - 0.5, rng() - 0.5, rng() - 0.5).multiplyScalar(j)))), s === 0 ? 1 : 0.6]);
    }
    const branches = 2 + Math.floor(rng() * 2);
    for (let q = 0; q < branches; q++) {
      const from = main[5 + Math.floor(rng() * (main.length - 10))];
      dir.subVectors(b, a).normalize();
      const bl = len * (0.2 + rng() * 0.3);
      side.set(rng() - 0.5, rng() - 0.5, rng() - 0.5).normalize();
      const to = from.clone().addScaledVector(dir, bl * 0.7).addScaledVector(side, bl * 0.7);
      paths.push([jagged(from, to, 3, 0.22), 0.5]);
    }
    let s = 0;
    const o0 = k * SEGS * 6;
    for (const [pts, w] of paths) {
      for (let i = 0; i < pts.length - 1 && s < SEGS; i++, s++) {
        posA.set([pts[i].x, pts[i].y, pts[i].z, pts[i + 1].x, pts[i + 1].y, pts[i + 1].z], o0 + s * 6);
        bolt.weight[s] = w * (w === 0.5 ? 1 - i / pts.length : 1);
      }
    }
    bolt.used = s;
    bolt.color = color.map((c) => c * 0.35 + 0.65);
    bolt.power = power;
    bolt.dur = 0.45 + rng() * 0.4;
    bolt.life = bolt.dur;
    bolt.next = 0;
    geo.attributes.position.needsUpdate = true;

    const fp = flashGeo.attributes.position.array, fc = flashGeo.attributes.color.array;
    fp.set([a.x, a.y, a.z, b.x, b.y, b.z], k * 6);
    fc.set([...bolt.color, ...bolt.color], k * 6);
    flashGeo.attributes.position.needsUpdate = true;
    flashGeo.attributes.color.needsUpdate = true;
  }

  function update(dt) {
    let any = false;
    const fa = flashGeo.attributes.aAlpha.array;
    bolts.forEach((bolt, k) => {
      const o0 = k * SEGS * 6;
      if (bolt.life <= 0) {
        if (bolt.used) colA.fill(0, o0, o0 + SEGS * 6), (bolt.used = 0), (fa[k * 2] = fa[k * 2 + 1] = 0), (any = true);
        return;
      }
      any = true;
      bolt.life -= dt;
      bolt.next -= dt;
      if (bolt.next <= 0) {
        bolt.flick = rng() < 0.25 ? 0.1 : 0.55 + rng() * 0.45;
        bolt.next = 0.04 + rng() * 0.05;
      }
      const fade = Math.max(0, bolt.life / bolt.dur);
      const I = 1.1 * bolt.power * bolt.flick * Math.pow(fade, 0.6);
      for (let s = 0; s < SEGS; s++) {
        const o = o0 + s * 6;
        const i = s < bolt.used ? I * bolt.weight[s] : 0;
        for (let q = 0; q < 3; q++) colA[o + q] = colA[o + 3 + q] = bolt.color[q] * i;
      }
      fa[k * 2] = 0.25 * I;
      fa[k * 2 + 1] = 0.45 * I;
    });
    if (any) {
      geo.attributes.color.needsUpdate = true;
      flashGeo.attributes.aAlpha.needsUpdate = true;
    }
  }

  return { strike, update, materials: [flashMat] };
}
