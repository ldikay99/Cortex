import * as THREE from 'three';
import { clamp, damp, smooth, mulberry32, gauss } from './rand.js';
import { pointsMaterial, linesMaterial, pointsGeometry } from './materials.js';

const SAMPLES = 24;
const STRANDS = 3;
const HAIRS = 16;
const SEGS_PER_LEG = (SAMPLES - 1) * STRANDS + HAIRS;

const HIP_ANG = [0.55, 1.1, 1.7, 2.35];
const REST_ANG = [0.4, 1.02, 1.98, 2.66];
const REST_R = [1.95, 1.6, 1.55, 1.9];
const LEG_LEN = [2.6, 2.15, 2.05, 2.5];
const MAX_STRETCH = 2.3;
const SCALE = 1.75;

const LEG_COLOR = [0.3, 0.9, 1.0];
const WARM = [0.78, 1.0, 1.0];

const _v = new THREE.Vector3();
const _w = new THREE.Vector3();
const _m = new THREE.Matrix4();
const _q = new THREE.Quaternion();

function ellipsoidWire(out, cx, cy, cz, rx, ry, rz, lat, lon, seg, shade) {
  const push = (a, b) => {
    out.pos.push(a[0], a[1], a[2], b[0], b[1], b[2]);
    for (const p of [a, b]) {
      const k = shade * (0.55 + 0.45 * ((p[1] - cy) / ry + 1) * 0.5);
      out.col.push(LEG_COLOR[0] * k, LEG_COLOR[1] * k, LEG_COLOR[2] * k);
    }
  };
  const S = (u, w) => {
    const r = Math.sqrt(Math.max(0, 1 - u * u));
    return [cx + rx * r * Math.sin(w), cy + ry * r * Math.cos(w), cz + rz * u];
  };
  for (let i = 1; i < lat; i++) {
    const u = -1 + (2 * i) / lat;
    for (let k = 0; k < seg; k++) push(S(u, (k / seg) * Math.PI * 2), S(u, ((k + 1) / seg) * Math.PI * 2));
  }
  for (let j = 0; j < lon; j++) {
    const w = (j / lon) * Math.PI * 2;
    for (let k = 0; k < seg; k++) push(S(-1 + (2 * k) / seg, w), S(-1 + (2 * (k + 1)) / seg, w));
  }
  return S;
}

function catmull(p0, p1, p2, p3, t, out) {
  const t2 = t * t, t3 = t2 * t;
  for (const c of ['x', 'y', 'z']) {
    out[c] = 0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2 + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3);
  }
  return out;
}

export function createSpider(scene, cosmos) {
  const rng = mulberry32(0xa11a);
  const group = new THREE.Group();
  group.scale.setScalar(SCALE);
  scene.add(group);
  const abdomen = new THREE.Group();
  abdomen.position.set(0, 0.06, -0.12);
  group.add(abdomen);

  const ceph = { pos: [], col: [] };
  ellipsoidWire(ceph, 0, 0.05, 0.14, 0.2, 0.11, 0.25, 5, 10, 20, 0.4);
  for (const s of [-1, 1]) {
    const a = [s * 0.05, 0.02, 0.36], b = [s * 0.06, -0.08, 0.44], c = [s * 0.04, -0.14, 0.42];
    ceph.pos.push(...a, ...b, ...b, ...c);
    for (let i = 0; i < 4; i++) ceph.col.push(0.16, 0.5, 0.56);
  }
  const abd = { pos: [], col: [] };
  const S = ellipsoidWire(abd, 0, 0.06, -0.3, 0.3, 0.24, 0.4, 6, 11, 24, 0.34);
  const mark = (pts, k) => {
    for (let i = 0; i < pts.length - 1; i++) {
      abd.pos.push(...pts[i], ...pts[i + 1]);
      abd.col.push(WARM[0] * k, WARM[1] * k, WARM[2] * k, WARM[0] * k, WARM[1] * k, WARM[2] * k);
    }
  };
  mark(Array.from({ length: 14 }, (_, i) => S(0.85 - i * 0.13, 0)), 0.32);
  for (const u0 of [0.4, 0.15, -0.1, -0.35, -0.58]) {
    for (const s of [-1, 1]) mark(Array.from({ length: 5 }, (_, i) => S(u0 - i * 0.05, s * i * 0.16)), 0.26);
  }
  for (const s of [-1, 1]) {
    abd.pos.push(...S(-0.97, s * 0.5), s * 0.03, 0.02, -0.76);
    abd.col.push(0.15, 0.48, 0.54, 0.11, 0.36, 0.4);
  }
  for (const s of [-1, 1]) {
    ceph.pos.push(s * 0.04, 0.06, -0.08, s * 0.05, 0.1, -0.03);
    ceph.col.push(0.14, 0.42, 0.48, 0.14, 0.42, 0.48);
  }
  const lineMat = linesMaterial();
  const mkLines = (data, parent) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));
    parent.add(new THREE.LineSegments(g, lineMat));
  };
  mkLines(ceph, group);
  mkLines(abd, abdomen);
  const onTop = (o) => (o.renderOrder = 10);

  const blob = (out, [cx, cy, cz], [rx, ry, rz], color, k, lat = 3, lon = 6, seg = 14) => {
    const P = (u, w) => {
      const r = Math.sqrt(Math.max(0, 1 - u * u));
      return [cx + rx * r * Math.sin(w), cy + ry * r * Math.cos(w), cz + rz * u];
    };
    const seg2 = (a, b) => {
      out.pos.push(...a, ...b);
      out.col.push(...color.map((c) => c * k), ...color.map((c) => c * k));
    };
    for (let i = 1; i < lat; i++) {
      const u = -1 + (2 * i) / lat;
      for (let j = 0; j < seg; j++) seg2(P(u, (j / seg) * Math.PI * 2), P(u, ((j + 1) / seg) * Math.PI * 2));
    }
    for (let i = 0; i < lon; i++) {
      const w = (i / lon) * Math.PI * 2;
      for (let j = 0; j < seg; j++) seg2(P(-1 + (2 * j) / seg, w), P(-1 + (2 * (j + 1)) / seg, w));
    }
  };
  const path = (out, pts, color, k) => {
    for (let i = 0; i < pts.length - 1; i++) {
      out.pos.push(...pts[i], ...pts[i + 1]);
      out.col.push(...color.map((c) => c * k), ...color.map((c) => c * k));
    }
  };
  const VIOLET = [0.78, 0.52, 1.0], MAGENTA = [1.0, 0.42, 0.72], AMBER = [1.0, 0.68, 0.28];
  const TEAL = [0.3, 1.0, 0.82], GOLD = [1.0, 0.92, 0.66], GREEN = [0.62, 1.0, 0.42], RED = [1.0, 0.32, 0.42];
  const head = { pos: [], col: [] };
  blob(head, [0, 0.08, 0.2], [0.06, 0.04, 0.055], VIOLET, 0.6, 3, 7);
  for (const sx of [-1, 1]) blob(head, [sx * 0.045, 0.03, 0.29], [0.022, 0.02, 0.05], MAGENTA, 0.55, 2, 5, 10);
  blob(head, [0, 0.03, 0.07], [0.07, 0.035, 0.06], AMBER, 0.45, 2, 6);
  const belly = { pos: [], col: [] };
  for (const sx of [-1, 1]) {
    for (let k = 0; k < 5; k++) {
      const y = -0.11 + k * 0.016;
      const ring = Array.from({ length: 13 }, (_, i) => {
        const a = (i / 12) * Math.PI * 2;
        return [sx * 0.13 + Math.cos(a) * 0.055, y, -0.05 + Math.sin(a) * 0.032];
      });
      path(belly, ring, TEAL, 0.45 - k * 0.04);
    }
  }
  const gut = Array.from({ length: 9 }, (_, i) => [0, 0.05 - i * 0.004, -0.02 - i * 0.07]);
  path(belly, gut, AMBER, 0.42);
  gut.slice(1, -1).forEach((p, i) => {
    for (const sx of [-1, 1]) path(belly, [p, [sx * 0.09, p[1] + 0.02, p[2] - 0.03], [sx * (0.16 + (i % 2) * 0.03), p[1] - 0.01, p[2] - 0.07]], AMBER, 0.3);
  });
  for (const sx of [-1, 1]) path(belly, Array.from({ length: 10 }, (_, i) => [sx * (0.05 + Math.sin(i * 1.3) * 0.04), -0.02 + Math.cos(i * 0.9) * 0.03, -0.3 - i * 0.03]), GREEN, 0.32);
  for (let k = 0; k < 6; k++) {
    const a = (k / 6) * Math.PI * 2;
    blob(belly, [Math.cos(a) * 0.06, -0.01 + Math.sin(a) * 0.04, -0.56 - (k % 2) * 0.04], [0.028, 0.028, 0.034], GOLD, 0.5, 2, 4, 8);
  }
  const organMat = linesMaterial();
  for (const [data, parent] of [[head, group], [belly, abdomen]]) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(data.pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(data.col, 3));
    parent.add(new THREE.LineSegments(g, organMat));
  }
  const heartData = { pos: [], col: [] };
  const HZ = Array.from({ length: 8 }, (_, i) => -0.02 - i * 0.075);
  for (const z of HZ) {
    const r = 0.026 + 0.012 * Math.sin(((z + 0.02) / 0.55) * Math.PI);
    path(heartData, Array.from({ length: 11 }, (_, i) => [Math.cos((i / 10) * Math.PI * 2) * r, 0.2 + Math.sin((i / 10) * Math.PI * 2) * r * 0.7, z]), RED, 0.85);
  }
  for (let i = 0; i < 4; i++) {
    const a = (i / 4) * Math.PI * 2;
    path(heartData, HZ.map((z) => [Math.cos(a) * 0.03, 0.2 + Math.sin(a) * 0.02, z]), RED, 0.7);
  }
  const heartMat = linesMaterial();
  const heartGeo = new THREE.BufferGeometry();
  heartGeo.setAttribute('position', new THREE.Float32BufferAttribute(heartData.pos, 3));
  heartGeo.setAttribute('color', new THREE.Float32BufferAttribute(heartData.col, 3));
  const heartMesh = new THREE.LineSegments(heartGeo, heartMat);
  abdomen.add(heartMesh);
  let heartKick = 0;

  const inner = 320;
  const eyes = 8;
  const bodyGeo = pointsGeometry(inner + eyes);
  {
    const p = bodyGeo.attributes.position.array, c = bodyGeo.attributes.color.array;
    const s = bodyGeo.attributes.aSize.array, a = bodyGeo.attributes.aAlpha.array;
    for (let i = 0; i < inner; i++) {
      const inAbd = i < inner * 0.66;
      let x, y, z;
      do {
        x = rng() * 2 - 1, y = rng() * 2 - 1, z = rng() * 2 - 1;
      } while (x * x + y * y + z * z > 1);
      if (inAbd) (x = x * 0.27), (y = 0.12 + y * 0.21), (z = -0.42 + z * 0.37);
      else (x = x * 0.18), (y = 0.05 + y * 0.1), (z = 0.14 + z * 0.23);
      p.set([x, y, z], i * 3);
      const warm = inAbd && rng() < 0.3;
      c.set(warm ? WARM : LEG_COLOR, i * 3);
      s[i] = 0.014 + rng() * 0.016;
      a[i] = 0.1 + rng() * 0.16;
    }
    const eyePos = [
      [-0.035, 0.155, 0.31], [0.035, 0.155, 0.31], [-0.075, 0.14, 0.29], [0.075, 0.14, 0.29],
      [-0.05, 0.13, 0.335], [0.05, 0.13, 0.335], [-0.1, 0.12, 0.26], [0.1, 0.12, 0.26],
    ];
    eyePos.forEach((e, k) => {
      const i = inner + k;
      p.set(e, i * 3);
      c.set([0.75, 1, 1], i * 3);
      s[i] = k < 2 ? 0.026 : 0.018;
      a[i] = 0.75;
    });
  }
  const bodyMat = pointsMaterial({ fog: 0.0016 });
  const bodyPts = new THREE.Points(bodyGeo, bodyMat);
  bodyPts.frustumCulled = false;
  group.add(bodyPts);

  const legs = [];
  for (let side = -1; side <= 1; side += 2) {
    for (let i = 0; i < 4; i++) {
      const ha = HIP_ANG[i], ra = REST_ANG[i];
      legs.push({
        side, i,
        hipL: new THREE.Vector3(side * Math.sin(ha) * 0.17, 0.04, 0.14 + Math.cos(ha) * 0.2),
        restL: new THREE.Vector3(side * Math.sin(ra) * REST_R[i], -0.55, Math.cos(ra) * REST_R[i] + 0.1),
        len: LEG_LEN[i] * SCALE,
        width: SCALE,
        foot: new THREE.Vector3(),
        hip: new THREE.Vector3(),
        ideal: new THREE.Vector3(),
        anchor: -1,
        step: null,
        search: rng() * 0.2,
        twist: rng() * Math.PI * 2,
        hairs: Array.from({ length: HAIRS }, () => ({ t: 0.12 + rng() * 0.8, a: rng() * Math.PI * 2 })),
        airL: i < 2
          ? new THREE.Vector3(side * (0.45 + i * 0.45), 0.2, 2.0 - i * 0.5)
          : new THREE.Vector3(side * (0.55 + (i - 2) * 0.3), -0.1, -1.3 - (i - 2) * 0.4),
        palp: false,
      });
    }
  }
  for (const side of [-1, 1]) {
    legs.push({
      side, i: -1,
      hipL: new THREE.Vector3(side * 0.07, 0.0, 0.34),
      restL: new THREE.Vector3(side * 0.17, -0.2, 0.68),
      len: 0.62 * SCALE, width: 0.55 * SCALE,
      foot: new THREE.Vector3(), hip: new THREE.Vector3(), ideal: new THREE.Vector3(),
      anchor: -1, step: null, search: 0, twist: rng() * 6,
      hairs: Array.from({ length: HAIRS }, () => ({ t: 0.2 + rng() * 0.7, a: rng() * Math.PI * 2 })),
      palp: true,
    });
  }
  const walkers = legs.filter((l) => !l.palp);

  const legSegs = legs.length * SEGS_PER_LEG;
  const legPos = new Float32Array(legSegs * 6);
  const legCol = new Float32Array(legSegs * 6);
  const legGeo = new THREE.BufferGeometry();
  legGeo.setAttribute('position', new THREE.BufferAttribute(legPos, 3));
  legGeo.setAttribute('color', new THREE.BufferAttribute(legCol, 3));
  const legLines = new THREE.LineSegments(legGeo, linesMaterial());
  legLines.frustumCulled = false;
  scene.add(legLines);
  onTop(legLines);

  const tipGeo = pointsGeometry(legs.length, { size: 0.045, alpha: 0.5, color: LEG_COLOR });
  const tipMat = pointsMaterial({ fog: 0.0016, heatSize: 1.2 });
  const tips = new THREE.Points(tipGeo, tipMat);
  tips.frustumCulled = false;
  scene.add(tips);
  onTop(tips);
  group.traverse(onTop);

  const glowTex = (stops) => {
    const cv = document.createElement('canvas');
    cv.width = cv.height = 128;
    const ctx = cv.getContext('2d');
    const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    for (const [at, col] of stops) g.addColorStop(at, col);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(cv);
  };
  const shade = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTex([[0, 'rgba(1,2,6,0.82)'], [0.45, 'rgba(1,2,6,0.55)'], [1, 'rgba(1,2,6,0)']]),
    transparent: true, depthWrite: false, depthTest: false,
  }));
  shade.scale.setScalar(4.2 * SCALE);
  shade.renderOrder = 5;
  scene.add(shade);
  const aura = new THREE.Sprite(new THREE.SpriteMaterial({
    map: glowTex([[0, 'rgba(90,230,255,0.22)'], [0.5, 'rgba(60,200,255,0.07)'], [1, 'rgba(0,0,0,0)']]),
    transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending,
  }));
  aura.scale.setScalar(2.4 * SCALE);
  aura.renderOrder = 6;
  scene.add(aura);

  const SILK = 32;
  const silkPos = new Float32Array(SILK * 6);
  const silkCol = new Float32Array(SILK * 6);
  const silkGeo = new THREE.BufferGeometry();
  silkGeo.setAttribute('position', new THREE.BufferAttribute(silkPos, 3));
  silkGeo.setAttribute('color', new THREE.BufferAttribute(silkCol, 3));
  const silkLine = new THREE.LineSegments(silkGeo, linesMaterial());
  silkLine.frustumCulled = false;
  silkLine.renderOrder = 10;
  silkLine.visible = false;
  scene.add(silkLine);
  const silk = { node: -1, life: 0, fading: false };
  const spinL = new THREE.Vector3(0, 0.03, -0.7);
  const spin = new THREE.Vector3();
  const silkP = new THREE.Vector3();

  function updateSilk(dt) {
    if (silk.node < 0) return;
    spin.copy(spinL).applyMatrix4(abdomen.matrixWorld);
    nodePos(silk.node, silkP);
    const d = spin.distanceTo(silkP);
    if (silk.fading || d > 50) silk.life -= dt / 3.5;
    else silk.life = Math.min(1, silk.life + dt * 2);
    if (silk.life <= 0) {
      silk.node = -1;
      silkLine.visible = false;
      return;
    }
    silkLine.visible = true;
    const sag = Math.min(0.9, d * 0.05);
    let prev = null;
    for (let k = 0; k <= SILK; k++) {
      const t = k / SILK;
      _v.copy(silkP).lerp(spin, t).addScaledVector(up, -Math.sin(Math.PI * t) * sag);
      _v.addScaledVector(fwd, Math.sin(clock * 1.4 + t * 9) * 0.03 * Math.sin(Math.PI * t));
      if (prev) {
        const o = (k - 1) * 6;
        silkPos.set([prev.x, prev.y, prev.z, _v.x, _v.y, _v.z], o);
        const i0 = 0.2 * silk.life * (0.35 + 0.65 * (t - 1 / SILK)), i1 = 0.2 * silk.life * (0.35 + 0.65 * t);
        silkCol.set([0.45 * i0, 0.9 * i0, i0, 0.45 * i1, 0.9 * i1, i1], o);
      }
      prev = (prev || new THREE.Vector3()).copy(_v);
    }
    silkGeo.attributes.position.needsUpdate = true;
    silkGeo.attributes.color.needsUpdate = true;
  }

  const pos = new THREE.Vector3();
  const vel = new THREE.Vector3();
  const fwd = new THREE.Vector3(0, 0, 1);
  const up = new THREE.Vector3(0, 1, 0);
  const quat = new THREE.Quaternion();
  let yawRate = 0;
  let crouch = 0;
  let jump = null;
  let clock = 0;
  let twitch = 1.5;

  const nodePos = (i, out) => out.set(cosmos.pos[i * 3], cosmos.pos[i * 3 + 1], cosmos.pos[i * 3 + 2]);
  const taken = (i, self) => legs.some((l) => l !== self && (l.anchor === i || (l.step && l.step.to === i)));
  const stepping = () => walkers.reduce((n, l) => n + (l.step ? 1 : 0), 0);
  const canStep = (leg) => {
    if (stepping() >= 3) return false;
    for (const o of walkers) {
      if (o === leg || !o.step) continue;
      if (o.side === leg.side && Math.abs(o.i - leg.i) === 1) return false;
      if (o.side !== leg.side && o.i === leg.i) return false;
    }
    return true;
  };
  const startStep = (leg, node, speedScale) => {
    const d = leg.foot.distanceTo(nodePos(node, _v));
    leg.step = {
      from: leg.foot.clone(),
      to: node,
      t: 0,
      dur: clamp(0.14 + d * 0.075, 0.15, 0.62) / speedScale,
      lift: (0.14 + Math.min(0.6, d * 0.12)) * SCALE,
    };
    leg.anchor = -1;
  };

  function place(p) {
    pos.copy(p);
    vel.set(0, 0, 0);
    group.position.copy(pos);
    group.quaternion.copy(quat);
    group.updateMatrixWorld(true);
    for (const leg of walkers) {
      leg.hip.copy(leg.hipL).applyMatrix4(group.matrixWorld);
      leg.ideal.copy(leg.restL).applyMatrix4(group.matrixWorld);
      const n = cosmos.nearest(leg.ideal.x, leg.ideal.y, leg.ideal.z, 3 * SCALE, (i) => taken(i, leg));
      leg.step = null;
      if (n >= 0) {
        leg.anchor = n;
        nodePos(n, leg.foot);
      } else {
        leg.anchor = -1;
        leg.foot.copy(leg.hip).lerp(leg.ideal, 0.5);
      }
    }
  }

  function launch() {
    const J = jump;
    J.phase = 'air';
    J.t = 0;
    J.from = pos.clone();
    const dist = J.from.distanceTo(J.to);
    const side = new THREE.Vector3().crossVectors(fwd, up).normalize();
    J.ctrl = J.from.clone().lerp(J.to, 0.5).addScaledVector(up, dist * J.arc).addScaledVector(side, (rng() - 0.5) * dist * 0.25);
    J.dur = clamp(dist / J.speed, J.min, J.max);
    for (const l of walkers) {
      if (l.i < 2 && l.anchor >= 0) cosmos.fire(l.anchor, 1.2), (l.anchor = -1);
      if (l.i < 2) l.step = null;
      l.search = 0.25;
    }
  }

  function land() {
    const J = jump;
    jump = null;
    vel.multiplyScalar(0.25);
    if (J.onLand) J.onLand();
    if (!J.burst) return;
    for (let k = 0; k < 5; k++) {
      const n = cosmos.nearest(pos.x + gauss(rng) * 0.9, pos.y + gauss(rng) * 0.9, pos.z + gauss(rng) * 0.9, 2.2);
      if (n >= 0) cosmos.fire(n, 1.1);
    }
    const from = cosmos.nearest(pos.x, pos.y, pos.z, 3);
    for (let k = 0; from >= 0 && k < 3; k++) {
      const to = cosmos.nearest(pos.x + gauss(rng) * 4, pos.y + gauss(rng) * 4, pos.z + gauss(rng) * 4, 3, (i) => i === from);
      if (to >= 0) cosmos.strike(from, to, 1.1);
    }
  }

  function moveJump(dt) {
    const J = jump;
    if (J.phase === 'crouch') {
      J.t += dt;
      vel.multiplyScalar(Math.exp(-dt * 6));
      pos.addScaledVector(vel, dt);
      fwd.lerp(_v.copy(J.to).sub(pos).normalize(), damp(5, dt)).normalize();
      crouch = smooth(Math.min(1, J.t / J.crouch));
      if (J.t >= J.crouch + 0.05) launch();
      return;
    }
    J.t += dt / J.dur;
    const t = Math.min(1, J.t), u = 1 - t;
    const s = 0.5 * smooth(t) + 0.5 * (1 - u * u);
    const w = 1 - s;
    _v.set(
      w * w * J.from.x + 2 * w * s * J.ctrl.x + s * s * J.to.x,
      w * w * J.from.y + 2 * w * s * J.ctrl.y + s * s * J.to.y,
      w * w * J.from.z + 2 * w * s * J.ctrl.z + s * s * J.to.z
    );
    vel.copy(_v).sub(pos).divideScalar(Math.max(dt, 1e-4));
    pos.copy(_v);
    crouch *= Math.exp(-dt * 8);
    if (t >= 1) land();
  }

  function updateBody(dt, time, goal, maxSpeed) {
    if (jump) moveJump(dt);
    else {
      const desired = _v.copy(goal).sub(pos).multiplyScalar(1.4);
      if (desired.length() > maxSpeed) desired.setLength(maxSpeed);
      vel.lerp(desired, damp(2.2, dt));
      pos.addScaledVector(vel, dt);
      crouch *= Math.exp(-dt * 6);
    }
    const speed = vel.length();

    const prevFwd = _w.copy(fwd);
    const airborne = jump && jump.phase === 'air';
    if (airborne) fwd.lerp(_v.copy(vel).divideScalar(Math.max(speed, 1e-4)), damp(4, dt)).normalize();
    else if (speed > 0.06 && !jump) fwd.lerp(_v.copy(vel).divideScalar(speed), damp(2.5 * Math.min(1, speed), dt)).normalize();
    const turn = prevFwd.cross(fwd).dot(up) / Math.max(dt, 1e-4);
    yawRate += (turn - yawRate) * damp(4, dt);

    let n = 0;
    const avg = _w.set(0, 0, 0);
    for (const l of walkers) if (l.anchor >= 0) avg.add(l.foot), n++;
    if (n >= 3) {
      avg.divideScalar(n).sub(pos).negate();
      if (avg.lengthSq() > 0.04) up.lerp(avg.normalize(), damp(0.9, dt));
    }
    up.lerp(_v.set(0, 1, 0), damp(0.25, dt));
    up.addScaledVector(fwd, -up.dot(fwd));
    if (up.lengthSq() < 0.01) up.set(0, 1, 0).addScaledVector(fwd, -fwd.y);
    up.normalize();

    const x = _v.crossVectors(up, fwd).normalize();
    _m.makeBasis(x, up, fwd);
    _q.setFromRotationMatrix(_m);
    quat.slerp(_q, damp(5, dt));

    const bob = Math.sin(time * 7.5) * 0.02 * Math.min(1, speed) + Math.sin(time * 1.3) * 0.012;
    group.position.copy(pos).addScaledVector(up, (bob - crouch * 0.22) * SCALE);
    group.quaternion.copy(quat);
    const breath = 1 + Math.sin(time * 1.6) * 0.018;
    abdomen.scale.set(breath, breath, 1 + (breath - 1) * 0.5);
    abdomen.rotation.y += (clamp(-yawRate * 0.35, -0.5, 0.5) - abdomen.rotation.y) * damp(3, dt);
    abdomen.rotation.x = Math.sin(time * 0.9) * 0.03 - Math.min(0.12, speed * 0.05) + crouch * 0.18;
    group.updateMatrixWorld(true);
    return speed;
  }

  function updateLegs(dt, time, speed) {
    const air = jump && jump.phase === 'air' ? jump : null;
    const lead = _w.copy(vel).multiplyScalar(air ? 0 : 0.4);
    const speedScale = clamp(0.8 + speed * 0.55, 0.8, 3.2);
    const reject = (leg) => (i) => taken(i, leg);

    for (const leg of legs) {
      leg.hip.copy(leg.hipL).applyMatrix4(group.matrixWorld);
      leg.ideal.copy(leg.restL).applyMatrix4(group.matrixWorld);
      if (leg.palp) {
        leg.ideal.addScaledVector(up, Math.sin(time * 2.1 + leg.side) * 0.05);
        leg.foot.lerp(leg.ideal, damp(10, dt));
        continue;
      }
      leg.ideal.add(lead);

      if (leg.step) {
        const st = leg.step;
        st.t += dt / st.dur;
        const k = smooth(Math.min(1, st.t));
        nodePos(st.to, _v);
        leg.foot.copy(st.from).lerp(_v, k).addScaledVector(up, st.lift * Math.sin(Math.PI * Math.min(1, st.t)));
        if (st.t >= 1) {
          leg.anchor = st.to;
          leg.step = null;
          leg.foot.copy(_v);
          cosmos.fire(leg.anchor, 0.7);
        }
        continue;
      }

      if (leg.anchor >= 0) {
        nodePos(leg.anchor, leg.foot);
        cosmos.hold(leg.anchor, 0.4);
        const dIdeal = leg.foot.distanceTo(leg.ideal);
        const reach = leg.foot.distanceTo(leg.hip);
        const b = leg.anchor * 3;
        _v.set(cosmos.base[b], cosmos.base[b + 1], cosmos.base[b + 2]);
        const pullAmt = clamp(0.03 + (reach / leg.len - 0.7) * 0.2, 0, 0.42) * SCALE;
        _v.lerp(leg.hip, pullAmt / Math.max(0.5, _v.distanceTo(leg.hip)));
        cosmos.pull(leg.anchor, _v.x, _v.y, _v.z);
        if (reach > leg.len * MAX_STRETCH) {
          leg.anchor = -1;
          cosmos.fire(b / 3, 0.9);
          continue;
        }
        if (jump) continue;
        if (dIdeal > 0.8 * SCALE && canStep(leg)) {
          const c = cosmos.nearest(leg.ideal.x, leg.ideal.y, leg.ideal.z, 1.6 * SCALE, reject(leg));
          if (c >= 0 && nodePos(c, _v).distanceTo(leg.ideal) < dIdeal - 0.35 * SCALE) startStep(leg, c, speedScale);
        }
        continue;
      }

      if (air) {
        _v.copy(leg.airL).applyMatrix4(group.matrixWorld);
        _v.addScaledVector(up, Math.sin(time * 5 + leg.twist) * 0.06);
        leg.foot.lerp(_v, damp(7, dt));
        leg.search -= dt;
        if (air.t > 0.72 && leg.search <= 0) {
          leg.search = 0.08;
          const c = cosmos.nearest(_v.x, _v.y, _v.z, leg.len * 1.3, reject(leg));
          if (c >= 0) startStep(leg, c, 2.4);
        }
        continue;
      }

      _v.copy(leg.hip).lerp(leg.ideal, 0.42).addScaledVector(up, 0.4 * SCALE);
      _v.x += Math.sin(time * 3 + leg.twist) * 0.08;
      _v.y += Math.cos(time * 2.4 + leg.twist) * 0.08;
      leg.foot.lerp(_v, damp(4, dt));
      leg.search -= dt;
      if (leg.search <= 0 && canStep(leg)) {
        leg.search = 0.12;
        const c = cosmos.nearest(leg.ideal.x, leg.ideal.y, leg.ideal.z, leg.len * 1.5, reject(leg));
        if (c >= 0) startStep(leg, c, speedScale * 0.8);
      }
    }

    if (speed < 0.08) {
      twitch -= dt;
      if (twitch <= 0) {
        twitch = 1.2 + rng() * 2.4;
        const leg = walkers[Math.floor(rng() * walkers.length)];
        if (leg.anchor >= 0 && canStep(leg)) {
          const c = cosmos.nearest(leg.ideal.x + (rng() - 0.5), leg.ideal.y + (rng() - 0.5), leg.ideal.z + (rng() - 0.5), 1.1 * SCALE, (i) => i === leg.anchor || taken(i, leg));
          if (c >= 0) startStep(leg, c, 0.7);
        }
      }
    }
  }

  const ctrl = Array.from({ length: 7 }, () => new THREE.Vector3());
  const samples = Array.from({ length: SAMPLES }, () => new THREE.Vector3());
  const T = new THREE.Vector3(), Sd = new THREE.Vector3(), B2 = new THREE.Vector3();
  const bend = new THREE.Vector3(), dir = new THREE.Vector3(), out = new THREE.Vector3();

  function drawLeg(leg, li) {
    const time = clock;
    const H = leg.hip, F = leg.foot;
    dir.subVectors(F, H);
    const d = Math.max(1e-3, dir.length());
    dir.divideScalar(d);
    bend.copy(up).addScaledVector(dir, -up.dot(dir));
    if (bend.lengthSq() < 0.01) bend.copy(fwd).addScaledVector(dir, -fwd.dot(dir));
    bend.normalize();
    out.copy(H).sub(group.position).addScaledVector(up, -out.dot(up));
    if (out.lengthSq() < 1e-6) out.copy(dir);
    out.normalize();

    const L = leg.len;
    const h = d < L ? Math.sqrt((L * L - d * d) / 4) : 0;
    const knee = Math.max(h, L * 0.03) * (1 + 0.035 * Math.sin(time * 2.6 + leg.twist * 3));
    ctrl[1].copy(H);
    ctrl[2].copy(H).addScaledVector(out, 0.07 * leg.width).addScaledVector(up, 0.05 * leg.width);
    ctrl[3].copy(H).addScaledVector(dir, d * 0.3).addScaledVector(bend, knee * 1.05);
    ctrl[4].copy(H).addScaledVector(dir, d * 0.68).addScaledVector(bend, knee * 0.55);
    ctrl[5].copy(F);
    ctrl[0].copy(ctrl[1]).multiplyScalar(2).sub(ctrl[2]);
    ctrl[6].copy(ctrl[5]).multiplyScalar(2).sub(ctrl[4]);
    for (let s = 0; s < SAMPLES; s++) {
      const f = (s / (SAMPLES - 1)) * 4;
      const seg = Math.min(3, Math.floor(f));
      catmull(ctrl[seg], ctrl[seg + 1], ctrl[seg + 2], ctrl[seg + 3], f - seg, samples[s]);
    }

    const tension = clamp((d - L) / L, 0, 1);
    const thin = clamp(L / d, 0.4, 1);
    const grip = leg.anchor >= 0 ? 1 : 0;
    const base = 0.56 + tension * 0.1;
    let o = li * SEGS_PER_LEG * 6;

    const strand = (j, s, target) => {
      const t = s / (SAMPLES - 1);
      const a = samples[Math.max(0, s - 1)], b = samples[Math.min(SAMPLES - 1, s + 1)];
      T.subVectors(b, a).normalize();
      Sd.crossVectors(T, bend).normalize();
      B2.crossVectors(Sd, T);
      const ang = (j / STRANDS) * Math.PI * 2 + leg.twist + t * 2.2;
      const w = 0.036 * leg.width * thin * Math.min(1, t * 9) * (1 - t * 0.82);
      return target.copy(samples[s]).addScaledVector(Sd, Math.cos(ang) * w).addScaledVector(B2, Math.sin(ang) * w);
    };
    const color = (t, k) => {
      const warm = Math.max(tension * 0.6, grip * Math.pow(t, 6) * 0.5);
      const i = base * k * (1 - t * 0.3);
      legCol[o] = (LEG_COLOR[0] * (1 - warm) + WARM[0] * warm) * i;
      legCol[o + 1] = (LEG_COLOR[1] * (1 - warm) + WARM[1] * warm) * i;
      legCol[o + 2] = (LEG_COLOR[2] * (1 - warm) + WARM[2] * warm) * i;
      o += 3;
    };
    const A = _v, B = _w;
    for (let j = 0; j < STRANDS; j++) {
      for (let s = 0; s < SAMPLES - 1; s++) {
        strand(j, s, A);
        strand(j, s + 1, B);
        legPos[o] = A.x, legPos[o + 1] = A.y, legPos[o + 2] = A.z;
        legPos[o + 3] = B.x, legPos[o + 4] = B.y, legPos[o + 5] = B.z;
        color(s / (SAMPLES - 1), 1);
        color((s + 1) / (SAMPLES - 1), 1);
      }
    }
    for (const hr of leg.hairs) {
      const s = Math.round(hr.t * (SAMPLES - 1));
      strand(Math.floor(hr.a) % STRANDS, s, A);
      const len = 0.1 * leg.width * (1 - hr.t * 0.6) * thin;
      B.copy(A).addScaledVector(Sd, Math.cos(hr.a) * len).addScaledVector(B2, Math.sin(hr.a) * len).addScaledVector(T, len * 0.9);
      legPos[o] = A.x, legPos[o + 1] = A.y, legPos[o + 2] = A.z;
      legPos[o + 3] = B.x, legPos[o + 4] = B.y, legPos[o + 5] = B.z;
      color(hr.t, 0.55);
      color(hr.t, 0.1);
    }

    const tp = tipGeo.attributes.position.array;
    tp[li * 3] = F.x, tp[li * 3 + 1] = F.y, tp[li * 3 + 2] = F.z;
    tipGeo.attributes.aHeat.array[li] = grip * 0.5 + tension * 0.5;
    tipGeo.attributes.aAlpha.array[li] = leg.palp ? 0.3 : 0.35 + grip * 0.25;
  }

  return {
    pos,
    materials: [bodyMat, tipMat],
    place,
    dropSilk() {
      spin.copy(spinL).applyMatrix4(abdomen.matrixWorld);
      const n = cosmos.nearest(spin.x, spin.y, spin.z, 3.5);
      if (n >= 0) Object.assign(silk, { node: n, life: silk.node === n ? silk.life : 0, fading: false });
    },
    releaseSilk() {
      silk.fading = true;
    },
    jump(target, { crouch = 0.5, speed = 13, min = 1.2, max = 3.2, arc = 0.22, burst = true, onLand = null } = {}) {
      if (jump && jump.onLand) jump.onLand();
      jump = { phase: 'crouch', t: 0, to: target.clone(), crouch, speed, min, max, arc, burst, onLand };
    },
    fwd,
    beat() {
      heartKick = 1;
    },
    get airborne() {
      return jump !== null;
    },
    get flying() {
      return !!jump && jump.phase === 'air';
    },
    update(dt, time, goal, maxSpeed) {
      clock = time;
      const speed = updateBody(dt, time, goal, maxSpeed);
      shade.position.copy(group.position);
      heartKick *= Math.exp(-dt * 4);
      const beat = Math.pow(Math.max(0, Math.sin(time * 8.5)), 12) * 0.5 + heartKick;
      heartMat.opacity = 0.55 + beat * 0.9;
      heartMesh.scale.set(1 + beat * 0.35, 1 + beat * 0.35, 1);
      aura.position.copy(group.position);
      aura.material.opacity = 0.85 + Math.sin(time * 2.2) * 0.15;
      updateSilk(dt);
      updateLegs(dt, time, speed);
      legs.forEach(drawLeg);
      legGeo.attributes.position.needsUpdate = true;
      legGeo.attributes.color.needsUpdate = true;
      tipGeo.attributes.position.needsUpdate = true;
      tipGeo.attributes.aHeat.needsUpdate = true;
      tipGeo.attributes.aAlpha.needsUpdate = true;
      return speed;
    },
  };
}
