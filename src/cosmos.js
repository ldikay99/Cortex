import * as THREE from 'three';
import { mulberry32, gauss } from './rand.js';
import { pointsMaterial, pointsGeometry } from './materials.js';
import { createGraph, EDGE, SHAPE, EDGE_BASE_OF } from './graph.js';
import { createLightning } from './lightning.js';

const SPREAD = 1.7;
const GROW = 1.8;
const NODE_SPREAD = 1.5;
const MORE = 2.6;
const MAX_GROWTH = 900;
const NEST_RADIUS = 5.5;
const SILK = [0.72, 0.92, 1.0];
export const BRIDGE_TINT = { http: [1.0, 0.68, 0.3], rpc: [0.26, 0.86, 0.76], event: [0.74, 0.5, 1.0], data: [0.5, 0.68, 1.0] };
const FLOW_KINDS = new Set(['http', 'rpc', 'event']);
const CROSS_KINDS = new Set(['import', 'call', 'contains', 'inherits', 'ref', 'loads']);
const TIER = { module: 0, doc: 0, endpoint: 0, topic: 0, class: 1, package: 1 };
const HTTP_VERB = /^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|ANY|ALL|WS|WEBSOCKET)\b/i;
export const isHttp = (n) => HTTP_VERB.test(n.route || n.name || '');

const DEMO = [
  { key: 'lenguaje', name: 'lenguaje', color: [0.58, 0.7, 1.0], center: [-13, 3.5, 3], n: 220, r: 2.4 },
  { key: 'memoria', name: 'memoria', color: [0.74, 0.6, 1.0], center: [12, 5, -4], n: 220, r: 2.5 },
  { key: 'afecto', name: 'afecto', color: [1.0, 0.58, 0.64], center: [3, -10, 5], n: 200, r: 2.3 },
  { key: 'decision', name: 'decisión', color: [0.54, 0.92, 0.84], center: [5, 2, 13], n: 200, r: 2.3 },
  { key: 'sensorial', name: 'sensorial', color: [0.5, 0.82, 1.0], center: [-4, -3, -13], n: 220, r: 2.5 },
  { key: 'sueno', name: 'sueño', color: [0.9, 0.62, 0.98], center: [-17, -9, -6], n: 190, r: 2.4 },
  { key: 'intuicion', name: 'intuición', color: [0.82, 0.96, 0.58], center: [17, -7, 8], n: 180, r: 2.3 },
  { key: 'imaginacion', name: 'imaginación', color: [1.0, 0.7, 0.42], center: [-9, 12, -10], n: 200, r: 2.5 },
  { key: 'instinto', name: 'instinto', color: [1.0, 0.5, 0.46], center: [9, 12, 10], n: 180, r: 2.3 },
].map((R) => ({ ...R, center: R.center.map((c) => c * SPREAD), r: R.r * GROW, n: Math.round(R.n * MORE) }));

function bez(ax, ay, az, cx, cy, cz, bx, by, bz, t, out, o = 0) {
  const s = 1 - t;
  out[o] = s * s * ax + 2 * s * t * cx + t * t * bx;
  out[o + 1] = s * s * ay + 2 * s * t * cy + t * t * by;
  out[o + 2] = s * s * az + 2 * s * t * cz + t * t * bz;
}

function randomBasis(rng) {
  const q = new THREE.Quaternion(gauss(rng), gauss(rng), gauss(rng), gauss(rng)).normalize();
  return new THREE.Matrix4().makeRotationFromQuaternion(q);
}

function pointPool(scene, capacity, mat) {
  const geo = pointsGeometry(capacity);
  geo.setDrawRange(0, 0);
  const pts = new THREE.Points(geo, mat);
  pts.frustumCulled = false;
  scene.add(pts);
  const a = geo.attributes;
  let n = 0;
  return {
    geo,
    get count() {
      return n;
    },
    push(x, y, z, c, size, alpha) {
      if (n >= capacity) return -1;
      a.position.array[n * 3] = x;
      a.position.array[n * 3 + 1] = y;
      a.position.array[n * 3 + 2] = z;
      a.color.array.set(c, n * 3);
      a.aSize.array[n] = size;
      a.aAlpha.array[n] = alpha;
      return n++;
    },
    flush() {
      geo.setDrawRange(0, n);
      a.position.needsUpdate = a.color.needsUpdate = a.aSize.needsUpdate = a.aAlpha.needsUpdate = true;
    },
  };
}

export function createCosmos(scene) {
  const rng = mulberry32(0x5eed1e);
  const graph = createGraph(scene);
  const lightning = createLightning(scene);
  const regions = [];
  const centers = [];
  const regionNodes = [];
  const shapes = [];
  const links = [];
  const meta = [];
  const tmp = new THREE.Vector3();
  const v = new THREE.Vector3();
  const w = new THREE.Vector3();
  let mode = 'nest';

  const starMat = pointsMaterial({ fog: 0.0008, maxPx: 8 });
  const dustMat = pointsMaterial({ fog: 0.0009, maxPx: 7 });
  const gasMat = pointsMaterial({ fog: 0.0007, maxPx: 520, heatSize: 0.25 });
  gasMat.uniforms.uHot.value.setRGB(0.86, 0.9, 1.0);
  const stars = pointPool(scene, 180000, starMat);
  const dust = pointPool(scene, 180000, dustMat);
  const gas = pointPool(scene, 5000, gasMat);

  const nodeVec = (i, out) => out.set(graph.base[i * 3], graph.base[i * 3 + 1], graph.base[i * 3 + 2]);
  const tint = (c, k) => c.map((x) => Math.min(1, x * k));

  const addNode = (x, y, z, r, color, size, alpha, animate = false) => {
    const id = graph.addNode(x, y, z, { region: r, color, size, alpha, animate });
    if (id >= 0 && r >= 0) regionNodes[r].push(id);
    return id;
  };

  const nebulaPoint = (center, radius, S, spread, out) => {
    if (rng() < 0.36) {
      out.set(gauss(rng) * radius * 0.34 * spread, gauss(rng) * radius * 0.24 * spread, gauss(rng) * radius * 0.34 * spread);
    } else {
      const arm = Math.floor(rng() * S.arms);
      const t = Math.pow(rng(), 0.85);
      const ang = (arm / S.arms) * Math.PI * 2 + t * S.twist;
      const rad = radius * (0.22 + t * 1.2);
      const j = radius * (0.06 + 0.16 * t) * spread;
      out.set(Math.cos(ang) * rad + gauss(rng) * j, gauss(rng) * radius * 0.13 * (1 - t * 0.4) * spread, Math.sin(ang) * rad + gauss(rng) * j);
    }
    return out.applyMatrix4(S.basis).add(center);
  };

  function addCommunity({ name, sub = '', color, center, radius, nodeRadius = radius * NODE_SPREAD, density = 1 }) {
    const i = regions.length;
    const c = new THREE.Vector3(...center);
    const S = { basis: randomBasis(rng), arms: 2 + Math.floor(rng() * 2), twist: 1.8 + rng() * 1.6 };
    const other = [rng(), rng(), rng()].map((x) => 0.5 + x * 0.5);
    const dustN = Math.round(Math.min(2200, Math.max(500, radius * 300)) * density);
    const starN = Math.round(Math.min(4200, Math.max(700, radius * 560)) * density);
    const gasN = Math.round(Math.min(70, Math.max(24, radius * 9)) * Math.min(1, density + 0.3));
    for (let k = 0; k < dustN; k++) {
      nebulaPoint(c, radius, S, 1.7, v);
      const m = rng() * 0.35;
      dust.push(v.x, v.y, v.z, color.map((x, q) => x * (1 - m) + other[q] * m), 0.025 + Math.pow(rng(), 4) * 0.08, 0.14 + rng() * 0.3);
    }
    for (let k = 0; k < starN; k++) {
      if (rng() < 0.5) {
        const r = Math.pow(rng(), 1.8) * radius * 0.75;
        v.set(gauss(rng), gauss(rng) * 0.75, gauss(rng)).normalize().multiplyScalar(r).applyMatrix4(S.basis).add(c);
      } else nebulaPoint(c, radius, S, 0.9, v);
      const k2 = rng() * 0.6;
      const bright = rng() < 0.04;
      stars.push(v.x, v.y, v.z, color.map((x) => x * (1 - k2) + k2), bright ? 0.09 + rng() * 0.05 : 0.032 + rng() * 0.034, bright ? 0.9 : 0.38 + rng() * 0.45);
    }
    const gasFrom = gas.count;
    for (let k = 0; k < gasN; k++) {
      nebulaPoint(c, radius, S, 0.8, v);
      const m = rng() * 0.5;
      gas.push(v.x, v.y, v.z, color.map((x, q) => x * (1 - m) + other[q] * m), radius * (0.5 + rng() * 0.9), 0.02 + rng() * 0.035);
    }
    stars.flush();
    dust.flush();
    gas.flush();
    regions.push({ name, sub, color, center, r: radius, nr: nodeRadius, gasFrom, gasCount: gas.count - gasFrom });
    centers.push(c);
    regionNodes.push([]);
    shapes.push(S);
    return i;
  }

  function buildNest() {
    const r = addCommunity({ name: 'núcleo', sub: 'nido de la araña', color: [0.62, 0.86, 1.0], center: [0, 0, 0], radius: 4.2, nodeRadius: NEST_RADIUS, density: 0.5 });
    const ico = new THREE.IcosahedronGeometry(NEST_RADIUS, 3).attributes.position;
    const ids = new Map();
    const vertex = (k) => {
      v.fromBufferAttribute(ico, k);
      const key = `${v.x.toFixed(3)},${v.y.toFixed(3)},${v.z.toFixed(3)}`;
      if (!ids.has(key)) {
        v.multiplyScalar(0.97 + rng() * 0.06);
        ids.set(key, addNode(v.x, v.y, v.z, r, tint(SILK, 0.85 + rng() * 0.2), 0.04 + rng() * 0.02, 0.6 + rng() * 0.25));
      }
      return ids.get(key);
    };
    for (let k = 0; k < ico.count; k += 3) {
      const a = vertex(k), b = vertex(k + 1), c = vertex(k + 2);
      graph.addEdge(a, b, { kind: EDGE.silk });
      graph.addEdge(b, c, { kind: EDGE.silk });
      graph.addEdge(c, a, { kind: EDGE.silk });
    }
    return r;
  }

  const kNearestIn = (i, list, k, maxD) => {
    const best = [];
    nodeVec(i, w);
    const m2 = maxD * maxD;
    for (const j of list) {
      if (j === i) continue;
      const d = nodeVec(j, v).distanceToSquared(w);
      if (d > m2) continue;
      if (best.length < k) best.push([j, d]);
      else {
        let q = 0;
        for (let z = 1; z < best.length; z++) if (best[z][1] > best[q][1]) q = z;
        if (d < best[q][1]) best[q] = [j, d];
      }
    }
    return best.map((b) => b[0]);
  };

  function seedDemo() {
    mode = 'demo';
    const first = regions.length;
    for (const R of DEMO) addCommunity({ name: R.name, color: R.color, center: R.center, radius: R.r });
    DEMO.forEach((R, k) => {
      const ri = first + k;
      for (let n = 0; n < R.n; n++) {
        nebulaPoint(centers[ri], R.r * NODE_SPREAD, shapes[ri], 1, v);
        const big = rng() < 0.05;
        addNode(v.x, v.y, v.z, ri, tint(R.color, 0.85 + rng() * 0.3), big ? 0.12 + rng() * 0.06 : 0.055 + rng() * 0.045, big ? 0.8 : 0.5 + rng() * 0.3);
      }
      const list = regionNodes[ri];
      for (const i of list) for (const j of kNearestIn(i, list, rng() < 0.35 ? 3 : 2, 2.4)) graph.addEdge(i, j, { kind: EDGE.intra });
    });

    const has = new Set();
    const link = (a, b) => {
      const key = a < b ? `${a},${b}` : `${b},${a}`;
      if (has.has(key)) return;
      has.add(key);
      const A = centers[a], B = centers[b];
      const d = A.distanceTo(B);
      const side = new THREE.Vector3(gauss(rng), gauss(rng), gauss(rng)).cross(B.clone().sub(A)).normalize();
      links.push({ a, b, ctrl: A.clone().add(B).multiplyScalar(0.5).addScaledVector(side, d * 0.14), len: d });
    };
    for (let i = first; i < regions.length; i++) {
      if (centers[i].length() < 15 * SPREAD) link(0, i);
      let best = -1, bd = Infinity;
      for (let j = first; j < regions.length; j++) {
        if (j !== i && centers[i].distanceTo(centers[j]) < bd) (bd = centers[i].distanceTo(centers[j])), (best = j);
      }
      link(i, best);
    }
    const out = [0, 0, 0];
    for (const L of links) {
      const RA = regions[L.a], RB = regions[L.b];
      const bridge = [];
      for (let k = 0; k < 24; k++) {
        const t = (k + rng()) / 24;
        bez(RA.center[0], RA.center[1], RA.center[2], L.ctrl.x, L.ctrl.y, L.ctrl.z, RB.center[0], RB.center[1], RB.center[2], t, out);
        gas.push(out[0] + gauss(rng) * 1.2, out[1] + gauss(rng) * 1.2, out[2] + gauss(rng) * 1.2, RA.color.map((c, q) => c * (1 - t) + RB.color[q] * t), 2.2 + rng() * 2.5, 0.02 + rng() * 0.022);
      }
      for (let s = 0; s < 3; s++) {
        const ax = RA.center[0] + gauss(rng) * RA.r * 0.35, ay = RA.center[1] + gauss(rng) * RA.r * 0.35, az = RA.center[2] + gauss(rng) * RA.r * 0.35;
        const bx = RB.center[0] + gauss(rng) * RB.r * 0.35, by = RB.center[1] + gauss(rng) * RB.r * 0.35, bz = RB.center[2] + gauss(rng) * RB.r * 0.35;
        const cx = L.ctrl.x + gauss(rng) * 1.8, cy = L.ctrl.y + gauss(rng) * 1.8, cz = L.ctrl.z + gauss(rng) * 1.8;
        for (let k = 0, dn = Math.floor(L.len * 24); k < dn; k++) {
          const t = rng();
          bez(ax, ay, az, cx, cy, cz, bx, by, bz, t, out);
          const sp = 0.1 + Math.abs(gauss(rng)) * 0.5;
          const m = Math.min(1, Math.max(0, t + (rng() - 0.5) * 0.2));
          dust.push(out[0] + gauss(rng) * sp, out[1] + gauss(rng) * sp, out[2] + gauss(rng) * sp, RA.color.map((c, q) => c * (1 - m) + RB.color[q] * m), 0.03 + Math.pow(rng(), 4) * 0.06, 0.32 + rng() * 0.4);
        }
        const count = Math.floor(L.len / 0.9);
        let prev = -1;
        for (let k = 1; k < count; k++) {
          const t = k / count + (rng() - 0.5) * 0.02;
          bez(ax, ay, az, cx, cy, cz, bx, by, bz, t, out);
          const id = addNode(out[0] + gauss(rng) * 0.3, out[1] + gauss(rng) * 0.3, out[2] + gauss(rng) * 0.3, -1, RA.color.map((c, q) => (c * (1 - t) + RB.color[q] * t) * 0.9), 0.04 + rng() * 0.025, 0.42 + rng() * 0.2);
          bridge.push(id);
          if (prev >= 0) graph.addEdge(prev, id, { kind: EDGE.bridge });
          else {
            const n = kNearestIn(id, regionNodes[L.a], 1, 99)[0];
            if (n !== undefined) graph.addEdge(n, id, { kind: EDGE.bridge });
          }
          prev = id;
        }
        const n = kNearestIn(prev, regionNodes[L.b], 1, 99)[0];
        if (n !== undefined) graph.addEdge(prev, n, { kind: EDGE.bridge });
      }
      for (const i of bridge) if (rng() < 0.35) for (const j of kNearestIn(i, bridge, 1, 1.5)) graph.addEdge(i, j, { kind: EDGE.bridge });
    }
    dust.flush();
    gas.flush();
  }

  const KIND_LOOK = {
    module: { size: 0.13, alpha: 0.88, white: 0.1 },
    doc: { size: 0.11, alpha: 0.8, white: 0.55 },
    class: { size: 0.09, alpha: 0.78, white: 0 },
    function: { size: 0.055, alpha: 0.5, white: 0 },
    method: { size: 0.05, alpha: 0.45, white: 0 },
    endpoint: { size: 0.15, alpha: 0.9, white: 0, shape: SHAPE.diamond, grow: 0.6 },
    package: { size: 0.13, alpha: 0.34, white: 0.45, shape: SHAPE.ring, grow: 0.4, fixed: [0.66, 0.72, 0.86], mix: 0.35 },
    variable: { size: 0.036, alpha: 0.6, white: 0, grow: 0.3, fixed: [1.0, 0.74, 0.4], mix: 0 },
    topic: { size: 0.075, alpha: 0.72, white: 0, grow: 0.6, fixed: [0.8, 0.64, 1.0], mix: 0 },
  };
  const projectNode = new Map();
  const alias = new Map();
  const callers = new Map();
  const tested = new Map();
  let endpointCount = 0;
  const lod = { bridges: 1, on: false, frac: [1, 1, 1], total: [0, 0, 0], kept: [0, 0, 0], seen: [0, 0, 0], hist: [new Uint32Array(65), new Uint32Array(65), new Uint32Array(65)], skipped: 0 };

  function planCapacity(stats) {
    const kinds = stats?.kinds;
    if (!kinds) return lod;
    const total = [0, 0, 0];
    lod.bridges = Math.min(1, Math.max(0.3, Math.sqrt(40 / Math.max(1, kinds.endpoint || 0))));
    for (const [k, c] of Object.entries(kinds)) total[TIER[k] ?? 2] += c;
    const budget = graph.capacity - graph.count - 1500;
    lod.total = total;
    if (total[0] + total[1] + total[2] <= budget) return lod;
    lod.on = true;
    lod.frac = [1, Math.min(1, Math.max(0, (budget - total[0]) / Math.max(1, total[1]))), Math.max(0, (budget - total[0] - total[1]) / Math.max(1, total[2]))];
    return lod;
  }

  function admit(n) {
    const t = TIER[n.kind] ?? 2;
    if (!lod.on || t === 0) return true;
    const f = lod.frac[t];
    if (f >= 1) return true;
    const d = Math.min(64, n.deg || 0);
    const h = lod.hist[t];
    h[d]++;
    lod.seen[t]++;
    if (f <= 0 || lod.kept[t] >= f * lod.total[t]) return false;
    let cum = 0, cut = 0;
    for (let k = 64; k >= 0; k--) {
      cum += h[k];
      if (cum / lod.seen[t] > f) {
        cut = k + 1;
        break;
      }
    }
    if (d < cut) return false;
    lod.kept[t]++;
    return true;
  }

  function aggregate(n) {
    const rep = projectNode.get(n.parent) ?? alias.get(n.parent);
    if (rep === undefined) return -1;
    alias.set(n.id, rep);
    if (meta[rep]) meta[rep].hidden = (meta[rep].hidden || 0) + 1;
    lod.skipped++;
    return -1;
  }

  function addProjectCommunity(c) {
    mode = 'project';
    return addCommunity({ name: c.name, sub: c.hub, color: c.color, center: c.center, radius: c.radius / NODE_SPREAD, nodeRadius: c.radius });
  }

  function satellite(n, region, out) {
    const c = centers[region];
    out.set(n.pos[0], n.pos[1], n.pos[2]).sub(c);
    if (out.lengthSq() < 1e-6) out.set(gauss(rng), gauss(rng) * 0.4, gauss(rng));
    return out.normalize().multiplyScalar(regions[region].nr * (1.25 + rng() * 0.35)).add(c);
  }

  function addProjectNode(n, region) {
    if (projectNode.has(n.id)) return projectNode.get(n.id);
    if (!(region >= 0) || !regions[region]) return -1;
    if (!admit(n)) return aggregate(n);
    const look = KIND_LOOK[n.kind] || KIND_LOOK.function;
    const R = regions[region];
    const mark = n.status === 'new' ? [0.55, 1.0, 0.72] : n.status === 'changed' ? [1.0, 0.74, 0.32] : null;
    const own = n.kind === 'endpoint' ? BRIDGE_TINT[isHttp(n) ? 'http' : 'rpc'] : look.fixed;
    const base = own ? own.map((x, q) => x * (1 - (look.mix || 0)) + R.color[q] * (look.mix || 0)) : R.color;
    const color = mark || base.map((x) => x * (1 - look.white) + look.white);
    const size = (look.size + Math.min(0.12, Math.log2(1 + (n.deg || 0)) * 0.012 * (look.grow ?? 1))) * (mark ? 1.5 : 1);
    const p = n.kind === 'package' ? satellite(n, region, tmp) : tmp.set(n.pos[0], n.pos[1], n.pos[2]);
    const alpha = look.alpha * (n.test ? 0.7 : 1);
    const id = graph.addNode(p.x, p.y, p.z, { region, color: tint(color, 0.9 + rng() * 0.2), size, alpha, animate: true, shape: look.shape || 0 });
    if (id < 0) return -1;
    regionNodes[region].push(id);
    projectNode.set(n.id, id);
    meta[id] = { ...n, region };
    if (n.kind === 'endpoint') endpointCount++;
    return id;
  }

  function addProjectEdge(e) {
    const a = projectNode.get(e.a) ?? alias.get(e.a), b = projectNode.get(e.b) ?? alias.get(e.b);
    if (a === undefined || b === undefined || a === b) return -1;
    if (e.kind === 'http' || e.kind === 'rpc') callers.set(b, (callers.get(b) || 0) + 1);
    if (e.kind === 'tests') tested.set(b, (tested.get(b) || 0) + 1);
    const cross = graph.region[a] !== graph.region[b];
    const kind = cross && CROSS_KINDS.has(e.kind) ? EDGE.cross : EDGE[e.kind] ?? EDGE.call;
    const tintOf = BRIDGE_TINT[e.kind] || null;
    const flow = FLOW_KINDS.has(e.kind);
    const strength = flow ? EDGE_BASE_OF(kind) * lod.bridges : null;
    return graph.addEdge(a, b, { kind, animate: true, tint: tintOf, arc: tintOf ? (cross ? 0.12 : 0.04) : 0, flow, strength });
  }

  function endpoints() {
    const out = [];
    meta.forEach((m, id) => {
      if (m && m.kind === 'endpoint') out.push({ id, m, callers: callers.get(id) || 0 });
    });
    return out.sort((x, y) => y.callers - x.callers || (x.m.route || x.m.name).localeCompare(y.m.route || y.m.name));
  }

  const STORMS = 6;
  const stormGeo = pointsGeometry(STORMS, { size: 1, alpha: 0, color: [0.8, 0.85, 1] });
  const stormMat = pointsMaterial({ fog: 0.0006, heatSize: 0, maxPx: 700 });
  {
    const pts = new THREE.Points(stormGeo, stormMat);
    pts.frustumCulled = false;
    scene.add(pts);
  }
  const gasPos = gas.geo.attributes.position.array;
  const gasHeat = gas.geo.attributes.aHeat.array;
  const storms = Array.from({ length: STORMS }, () => ({ active: false, t: 0, flashes: [], lit: [], center: new THREE.Vector3(), size: 1 }));
  let stormT = 1;

  function startStorm(r) {
    const s = storms.find((x) => !x.active);
    const R = regions[r];
    if (!s || !R || !R.gasCount) return;
    const gi = R.gasFrom + Math.floor(rng() * R.gasCount);
    s.center.set(gasPos[gi * 3], gasPos[gi * 3 + 1], gasPos[gi * 3 + 2]);
    s.size = R.r * (0.45 + rng() * 0.4);
    s.color = R.color.map((c) => c * 0.35 + 0.65);
    s.lit = [];
    for (let i = R.gasFrom; i < R.gasFrom + R.gasCount; i++) {
      const d = Math.hypot(gasPos[i * 3] - s.center.x, gasPos[i * 3 + 1] - s.center.y, gasPos[i * 3 + 2] - s.center.z);
      if (d < s.size * 1.6) s.lit.push([i, 1 - d / (s.size * 1.6)]);
    }
    s.flashes = [];
    let at = 0;
    for (let k = 0, n = 2 + Math.floor(rng() * 4); k < n; k++) {
      s.flashes.push({ at, dur: 0.07 + rng() * 0.16, power: 0.5 + rng() * 0.5, bolt: rng() < 0.45, done: false });
      at += 0.08 + rng() * 0.35;
    }
    s.end = at + 0.3;
    s.t = 0;
    s.active = true;
    const k = storms.indexOf(s);
    stormGeo.attributes.position.array.set([s.center.x, s.center.y, s.center.z], k * 3);
    stormGeo.attributes.color.array.set(s.color, k * 3);
    stormGeo.attributes.aSize.array[k] = s.size * 2.4;
    stormGeo.attributes.position.needsUpdate = stormGeo.attributes.color.needsUpdate = stormGeo.attributes.aSize.needsUpdate = true;
  }

  function updateStorms(dt) {
    const alpha = stormGeo.attributes.aAlpha.array;
    let touched = false;
    storms.forEach((s, k) => {
      if (!s.active) return;
      s.t += dt;
      let I = 0;
      for (const f of s.flashes) {
        const u = (s.t - f.at) / f.dur;
        if (u >= 0 && u <= 1) I = Math.max(I, f.power * Math.pow(1 - u, 0.6) * (0.75 + rng() * 0.25));
        if (f.bolt && !f.done && u >= 0) {
          f.done = true;
          v.copy(s.center).add(tmp.set(gauss(rng), gauss(rng), gauss(rng)).multiplyScalar(s.size * 0.35));
          w.copy(v).add(tmp.set(gauss(rng), gauss(rng), gauss(rng)).normalize().multiplyScalar(s.size * (0.5 + rng() * 0.6)));
          lightning.strike(v, w, s.color, 0.55);
        }
      }
      alpha[k] = 0.2 * I;
      for (const [i, wgt] of s.lit) gasHeat[i] = wgt * I * 3.5;
      touched = true;
      if (s.t >= s.end) {
        s.active = false;
        alpha[k] = 0;
        for (const [i] of s.lit) gasHeat[i] = 0;
      }
    });
    if (touched) {
      stormGeo.attributes.aAlpha.needsUpdate = true;
      gas.geo.attributes.aHeat.needsUpdate = true;
    }
  }

  let focus = 0;
  let boltT = 0.6;
  let growT = 2.5;
  const grown = [];
  const pa = new THREE.Vector3();
  const pb = new THREE.Vector3();

  function strikeNodes(a, b, power = 1) {
    nodeVec(a, pa);
    nodeVec(b, pb);
    const ra = graph.region[a], rb = graph.region[b];
    const col = (regions[ra >= 0 ? ra : rb >= 0 ? rb : 0] || regions[0]).color;
    lightning.strike(pa, pb, col, power);
    graph.fire(a, 0.6 * power);
    graph.fire(b, 1.0 * power);
  }

  function ambientBolt() {
    const r = rng() < 0.6 ? focus : Math.floor(rng() * regions.length);
    const list = regionNodes[r];
    if (!list || list.length < 4) return;
    const a = list[Math.floor(rng() * list.length)];
    nodeVec(a, w);
    let best = -1, bd = 0;
    for (let k = 0; k < 24; k++) {
      const c = list[Math.floor(rng() * list.length)];
      const d = nodeVec(c, v).distanceTo(w);
      if (d > 3 && d < 10 && d > bd) (bd = d), (best = c);
    }
    if (best >= 0) strikeNodes(a, best, 0.8 + rng() * 0.4);
  }

  function spawn(r, parent = -1) {
    const R = regions[r];
    const list = regionNodes[r];
    if (graph.full || !list || !list.length) return -1;
    for (let tries = 0; tries < 4; tries++) {
      const p = parent >= 0 ? parent : list[Math.floor(rng() * list.length)];
      nodeVec(p, w);
      v.copy(w).sub(centers[r]).normalize().add(tmp.set(gauss(rng), gauss(rng), gauss(rng)).multiplyScalar(0.5)).normalize();
      v.multiplyScalar(0.9 + rng() * 1.3).add(w);
      if (parent < 0 && v.distanceTo(centers[r]) > R.nr * 2.1) continue;
      const big = rng() < 0.08;
      const id = addNode(v.x, v.y, v.z, r, tint(R.color, 0.95 + rng() * 0.25), big ? 0.13 : 0.06 + rng() * 0.04, big ? 0.85 : 0.6 + rng() * 0.25, true);
      if (id < 0) return -1;
      graph.addEdge(p, id, { kind: EDGE.intra, animate: true });
      for (const j of graph.kNearest(v.x, v.y, v.z, 3, 2.8, (i) => i === id || i === p)) graph.addEdge(id, j, { kind: EDGE.intra, animate: true });
      strikeNodes(p, id, 1);
      grown[r] = (grown[r] || 0) + 1;
      return id;
    }
    return -1;
  }

  buildNest();

  return {
    graph,
    meta,
    pos: graph.pos,
    base: graph.base,
    nodeRegion: graph.region,
    regionNodes,
    links,
    regions,
    centers,
    materials: [...graph.materials, ...lightning.materials, dustMat, gasMat, starMat, stormMat],
    boostMaterials: [graph.nodeMat, starMat],
    lineMaterials: [graph.lineMat],
    get count() {
      return graph.count;
    },
    fire: graph.fire,
    hold: graph.hold,
    pull: graph.pull,
    nearest: graph.nearest,
    seedDemo,
    addProjectCommunity,
    addProjectNode,
    addProjectEdge,
    planCapacity,
    endpoints,
    lod,
    get endpointCount() {
      return endpointCount;
    },
    callersOf: (id) => callers.get(id) || 0,
    testsOf: (id) => tested.get(id) || 0,
    nodeOf: (sid) => projectNode.get(sid) ?? alias.get(sid) ?? -1,
    spawn,
    strike: strikeNodes,

    setFocus(r) {
      if (r >= 0) focus = r;
    },

    regionAt(p) {
      let best = -1, bd = Infinity;
      regions.forEach((R, i) => {
        const d = p.distanceTo(centers[i]) / (R.nr * 1.3);
        if (d < bd) (bd = d), (best = i);
      });
      return bd < 1.6 ? best : -1;
    },

    update(dt) {
      if (graph.count && rng() < dt * 2.6) graph.fire(Math.floor(rng() * graph.count), 0.32 + rng() * 0.25);
      boltT -= dt;
      if (boltT <= 0) {
        boltT = 1.2 + rng() * 1.6;
        ambientBolt();
      }
      stormT -= dt;
      if (stormT <= 0) {
        stormT = 0.8 + rng() * 1.8;
        startStorm(rng() < 0.35 ? focus : Math.floor(rng() * regions.length));
      }
      updateStorms(dt);
      if (mode === 'demo') {
        growT -= dt;
        if (growT <= 0) {
          growT = 1.4 + rng() * 1.4;
          const r = rng() < 0.65 ? focus : 1 + Math.floor(rng() * (regions.length - 1));
          if ((grown[r] || 0) < MAX_GROWTH) spawn(r);
        }
      }
      graph.update(dt);
      lightning.update(dt);
    },
  };
}
