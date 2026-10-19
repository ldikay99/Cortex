import * as THREE from 'three';
import { mulberry32, gauss, smooth } from './rand.js';
import { pointsMaterial, linesMaterial, pointsGeometry } from './materials.js';

const SEG = 4;
const CELL = 2;
const MAX_PULSES = 1200;
const PULSE_SPEED = 3.8;
const NODE_IN = 0.9;
const EDGE_IN = 0.7;
const CHUNK = 512;
const CHUNK_FLOATS = CHUNK * SEG * 6;
const MAX_FLOWS = 900;
const FLOW_SPEED = 2.2;

export const EDGE = {
  intra: 0, bridge: 1, import: 2, call: 3, contains: 4, inherits: 5, ref: 6, loads: 6, silk: 7, cross: 8,
  http: 9, rpc: 10, handles: 11, data: 12, event: 13, env: 14, depends: 15, tests: 16, cochange: 17,
};
const EDGE_BASE = [0.13, 0.15, 0.085, 0.045, 0.04, 0.07, 0.06, 0.2, 0.022, 0.12, 0.12, 0.05, 0.035, 0.1, 0, 0, 0, 0];
export const SHAPE = { dot: 0, ring: 1, diamond: 2 };
export const EDGE_BASE_OF = (kind) => EDGE_BASE[kind] ?? 0.13;

function bez(ax, ay, az, cx, cy, cz, bx, by, bz, t, out, o = 0) {
  const s = 1 - t;
  out[o] = s * s * ax + 2 * s * t * cx + t * t * bx;
  out[o + 1] = s * s * ay + 2 * s * t * cy + t * t * by;
  out[o + 2] = s * s * az + 2 * s * t * cz + t * t * bz;
}

export function createGraph(scene, { maxNodes = 120000, maxEdges = 140000, seed = 0x9a7 } = {}) {
  const rng = mulberry32(seed);
  let n = 0;
  let m = 0;

  const base = new Float32Array(maxNodes * 3);
  const pos = new Float32Array(maxNodes * 3);
  const disp = new Float32Array(maxNodes * 3);
  const dvel = new Float32Array(maxNodes * 3);
  const heat = new Float32Array(maxNodes);
  const refr = new Float32Array(maxNodes);
  const region = new Int16Array(maxNodes).fill(-1);
  const alphaT = new Float32Array(maxNodes);
  const color = new Float32Array(maxNodes * 3);
  const adj = [];
  const newborn = new Map();
  const grid = new Map();
  const pullT = new Map();
  const moving = new Set();

  const nodeGeo = pointsGeometry(maxNodes);
  nodeGeo.setAttribute('aShape', new THREE.BufferAttribute(new Float32Array(maxNodes), 1));
  nodeGeo.setDrawRange(0, 0);
  const nodeMat = pointsMaterial({ fog: 0.0009, heatSize: 0.9, shapes: true });
  const nodePoints = new THREE.Points(nodeGeo, nodeMat);
  nodePoints.frustumCulled = false;
  scene.add(nodePoints);

  const ea = new Int32Array(maxEdges);
  const eb = new Int32Array(maxEdges);
  const ekind = new Uint8Array(maxEdges);
  const ectrl = new Float32Array(maxEdges * 3);
  const elen = new Float32Array(maxEdges);
  const lineBase = new Float32Array(maxEdges);
  const glow = new Float32Array(maxEdges);
  const grow = new Float32Array(maxEdges);
  const edgeSet = new Set();
  const lit = new Set();
  const growing = new Set();
  const linePos = new Float32Array(maxEdges * SEG * 6);
  const lineTint = new Float32Array(maxEdges * SEG * 6);
  const lineCol = new Float32Array(maxEdges * SEG * 6);
  const posChunks = new Uint8Array(Math.ceil(maxEdges / CHUNK));
  const colChunks = new Uint8Array(posChunks.length);
  let posDirty = false;
  let colDirty = false;
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3));
  lineGeo.setAttribute('color', new THREE.BufferAttribute(lineCol, 3));
  lineGeo.setDrawRange(0, 0);
  const lines = new THREE.LineSegments(lineGeo, linesMaterial());
  lines.frustumCulled = false;
  scene.add(lines);

  const pulseGeo = pointsGeometry(MAX_PULSES, { size: 0.07, alpha: 0.85, color: [1, 0.95, 0.86] });
  pulseGeo.setDrawRange(0, 0);
  const pulseMat = pointsMaterial({ fog: 0.0009, heatSize: 0 });
  const pulsePoints = new THREE.Points(pulseGeo, pulseMat);
  pulsePoints.frustumCulled = false;
  scene.add(pulsePoints);
  const pulses = [];

  const flowGeo = pointsGeometry(MAX_FLOWS, { size: 0.06, alpha: 0, color: [1, 0.9, 0.7] });
  flowGeo.setDrawRange(0, 0);
  const flowMat = pointsMaterial({ fog: 0.0009, heatSize: 0 });
  const flowPoints = new THREE.Points(flowGeo, flowMat);
  flowPoints.frustumCulled = false;
  scene.add(flowPoints);
  const flows = [];

  const cellKey = (ix, iy, iz) => ((ix + 512) * 1024 + (iy + 512)) * 1024 + (iz + 512);
  const cellOf = (v) => Math.floor(v / CELL);

  function edgePoint(e, t, out, o = 0) {
    const a = ea[e] * 3, b = eb[e] * 3, c = e * 3;
    bez(
      pos[a], pos[a + 1], pos[a + 2],
      ectrl[c] + (disp[a] + disp[b]) * 0.5, ectrl[c + 1] + (disp[a + 1] + disp[b + 1]) * 0.5, ectrl[c + 2] + (disp[a + 2] + disp[b + 2]) * 0.5,
      pos[b], pos[b + 1], pos[b + 2], t, out, o
    );
  }

  function writeEdge(e) {
    const g = grow[e];
    posChunks[(e / CHUNK) | 0] = 1;
    posDirty = true;
    for (let s = 0; s < SEG; s++) {
      const o = (e * SEG + s) * 6;
      edgePoint(e, (s / SEG) * g, linePos, o);
      edgePoint(e, ((s + 1) / SEG) * g, linePos, o + 3);
    }
  }

  function writeEdgeColor(e) {
    const gl = glow[e] * 0.55;
    const k = lineBase[e] * (0.4 + 0.6 * grow[e]) + gl;
    const o0 = e * SEG * 6;
    for (let j = 0; j < SEG * 6; j++) lineCol[o0 + j] = lineTint[o0 + j] * k + gl * 0.25;
    colChunks[(e / CHUNK) | 0] = 1;
    colDirty = true;
  }

  function flushChunks(attr, chunks) {
    attr.clearUpdateRanges();
    const limit = m * SEG * 6;
    for (let c = 0; c < chunks.length; c++) {
      if (!chunks[c]) continue;
      let end = c;
      while (end + 1 < chunks.length && chunks[end + 1]) end++;
      const start = c * CHUNK_FLOATS;
      const count = Math.min(limit, (end + 1) * CHUNK_FLOATS) - start;
      if (count > 0) attr.addUpdateRange(start, count);
      chunks.fill(0, c, end + 1);
      c = end;
    }
    attr.needsUpdate = true;
  }

  function spread(i, amp, skipEdge) {
    if (refr[i] > 0 || amp < 0.12) return;
    refr[i] = 0.45;
    const list = adj[i];
    let spawned = 0;
    const p = amp > 0.6 ? 0.9 : 0.55;
    for (let k = 0; k < list.length && spawned < 4; k++) {
      const e = list[(k + Math.floor(rng() * list.length)) % list.length];
      if (e === skipEdge || grow[e] < 1 || rng() > p || pulses.length >= MAX_PULSES) continue;
      pulses.push({ e, dir: ea[e] === i ? 1 : -1, u: 0, amp: amp * 0.62 });
      spawned++;
    }
  }

  let hot = -1;
  let hotSize = 0;
  let selected = -1;

  const glowAround = (i) => {
    heat[i] = Math.max(heat[i], 1);
    for (const e of adj[i]) {
      if (glow[e] < 0.75) glow[e] = 0.75;
      lit.add(e);
    }
  };

  const api = {
    pos, base, region,

    setHot(i) {
      if (i === hot) return;
      const sz = nodeGeo.attributes.aSize;
      if (hot >= 0) sz.array[hot] = hotSize;
      hot = i;
      if (i >= 0) {
        hotSize = sz.array[i];
        sz.array[i] = hotSize * 2.6 + 0.08;
      }
      sz.needsUpdate = true;
    },
    setSelected(i) {
      selected = i;
    },
    get selected() {
      return selected;
    },
    neighbors(i, kinds) {
      const out = [];
      for (const e of adj[i] || []) if (!kinds || kinds.includes(ekind[e])) out.push({ node: ea[e] === i ? eb[e] : ea[e], kind: ekind[e], out: ea[e] === i });
      return out;
    },
    get flows() {
      return flows.length;
    },
    materials: [nodeMat, pulseMat, flowMat],
    nodeMat,
    lineMat: lines.material,
    get count() {
      return n;
    },
    get edges() {
      return m;
    },
    capacity: maxNodes,
    get full() {
      return n >= maxNodes - 1 || m >= maxEdges - 8;
    },

    addNode(x, y, z, { region: r = -1, color: c = [1, 1, 1], size = 0.06, alpha = 0.6, animate = false, shape = 0 } = {}) {
      if (n >= maxNodes) return -1;
      const i = n++;
      base[i * 3] = pos[i * 3] = x;
      base[i * 3 + 1] = pos[i * 3 + 1] = y;
      base[i * 3 + 2] = pos[i * 3 + 2] = z;
      region[i] = r;
      color.set(c, i * 3);
      alphaT[i] = alpha;
      adj.push([]);
      const g = nodeGeo.attributes;
      g.position.array.set([x, y, z], i * 3);
      g.color.array.set(c, i * 3);
      g.aSize.array[i] = size;
      g.aAlpha.array[i] = animate ? 0 : alpha;
      g.aShape.array[i] = shape;
      g.aShape.needsUpdate = true;
      if (animate) {
        newborn.set(i, 0);
        heat[i] = 1.2;
      }
      g.position.needsUpdate = g.color.needsUpdate = g.aSize.needsUpdate = g.aAlpha.needsUpdate = true;
      nodeGeo.setDrawRange(0, n);
      const key = cellKey(cellOf(x), cellOf(y), cellOf(z));
      const cell = grid.get(key);
      if (cell) cell.push(i);
      else grid.set(key, [i]);
      return i;
    },

    addEdge(a, b, { kind = 0, animate = false, tint = null, arc = 0, flow = false, strength = null } = {}) {
      if (a === b || a < 0 || b < 0 || m >= maxEdges) return -1;
      const key = a < b ? a * 1048576 + b : b * 1048576 + a;
      if (edgeSet.has(key)) return -1;
      edgeSet.add(key);
      const e = m++;
      ea[e] = a;
      eb[e] = b;
      ekind[e] = kind;
      const ax = base[a * 3], ay = base[a * 3 + 1], az = base[a * 3 + 2];
      const bx = base[b * 3], by = base[b * 3 + 1], bz = base[b * 3 + 2];
      const len = Math.hypot(bx - ax, by - ay, bz - az);
      const bend = len * (0.03 + rng() * 0.07);
      ectrl[e * 3] = (ax + bx) / 2 + gauss(rng) * bend;
      ectrl[e * 3 + 1] = (ay + by) / 2 + gauss(rng) * bend + len * arc;
      ectrl[e * 3 + 2] = (az + bz) / 2 + gauss(rng) * bend;
      elen[e] = len * 1.05;
      lineBase[e] = strength ?? EDGE_BASE[kind] ?? 0.13;
      grow[e] = animate ? 0 : 1;
      for (let s = 0; s < SEG; s++) {
        const o = (e * SEG + s) * 6;
        const t0 = s / SEG, t1 = (s + 1) / SEG;
        for (let q = 0; q < 3; q++) {
          const ca = tint ? tint[q] : color[a * 3 + q], cb = tint ? tint[q] : color[b * 3 + q];
          lineTint[o + q] = ca * (1 - t0) + cb * t0;
          lineTint[o + 3 + q] = ca * (1 - t1) + cb * t1;
        }
      }
      writeEdge(e);
      writeEdgeColor(e);
      if (animate) growing.add(e), lit.add(e);
      adj[a].push(e);
      adj[b].push(e);
      if (flow && flows.length < MAX_FLOWS) {
        const k = flows.length;
        flows.push({ e, u: rng(), rate: Math.min(0.2, FLOW_SPEED / Math.max(1, elen[e])) });
        flowGeo.attributes.color.array.set(tint || [color[a * 3], color[a * 3 + 1], color[a * 3 + 2]], k * 3);
        flowGeo.attributes.color.needsUpdate = true;
      }
      lineGeo.setDrawRange(0, m * SEG * 2);
      return e;
    },


    nearest(x, y, z, radius, reject) {
      let best = -1;
      let bd = radius * radius;
      const rc = Math.ceil((radius + 0.6) / CELL);
      const cx = cellOf(x), cy = cellOf(y), cz = cellOf(z);
      for (let ix = cx - rc; ix <= cx + rc; ix++) {
        for (let iy = cy - rc; iy <= cy + rc; iy++) {
          for (let iz = cz - rc; iz <= cz + rc; iz++) {
            const cell = grid.get(cellKey(ix, iy, iz));
            if (!cell) continue;
            for (const i of cell) {
              const dx = pos[i * 3] - x, dy = pos[i * 3 + 1] - y, dz = pos[i * 3 + 2] - z;
              const d = dx * dx + dy * dy + dz * dz;
              if (d < bd && !(reject && reject(i))) (bd = d), (best = i);
            }
          }
        }
      }
      return best;
    },

    kNearest(x, y, z, k, radius, reject) {
      const found = [];
      const rc = Math.ceil(radius / CELL);
      const cx = cellOf(x), cy = cellOf(y), cz = cellOf(z);
      const r2 = radius * radius;
      for (let ix = cx - rc; ix <= cx + rc; ix++) {
        for (let iy = cy - rc; iy <= cy + rc; iy++) {
          for (let iz = cz - rc; iz <= cz + rc; iz++) {
            const cell = grid.get(cellKey(ix, iy, iz));
            if (!cell) continue;
            for (const i of cell) {
              const dx = base[i * 3] - x, dy = base[i * 3 + 1] - y, dz = base[i * 3 + 2] - z;
              const d = dx * dx + dy * dy + dz * dz;
              if (d < r2 && !(reject && reject(i))) found.push([i, d]);
            }
          }
        }
      }
      found.sort((p, q) => p[1] - q[1]);
      return found.slice(0, k).map((f) => f[0]);
    },

    fire(i, amp = 1) {
      heat[i] = Math.min(1.3, heat[i] + amp);
      spread(i, amp, -1);
    },

    hold(i, level) {
      if (heat[i] < level) heat[i] = level;
    },

    pull(i, x, y, z) {
      pullT.set(i, [x - base[i * 3], y - base[i * 3 + 1], z - base[i * 3 + 2]]);
      moving.add(i);
    },

    update(dt) {
      if (hot >= 0) glowAround(hot);
      if (selected >= 0 && selected < n) glowAround(selected);
      const hd = Math.exp(-dt * 2.4);
      for (let i = 0; i < n; i++) {
        heat[i] *= hd;
        if (refr[i] > 0) refr[i] -= dt;
      }

      if (newborn.size) {
        const al = nodeGeo.attributes.aAlpha.array;
        for (const [i, age] of newborn) {
          const a = age + dt;
          al[i] = alphaT[i] * smooth(Math.min(1, a / NODE_IN));
          if (a >= NODE_IN) newborn.delete(i);
          else newborn.set(i, a);
        }
        nodeGeo.attributes.aAlpha.needsUpdate = true;
      }

      const pp = pulseGeo.attributes.position.array;
      const pa = pulseGeo.attributes.aAlpha.array;
      let w = 0;
      for (let k = 0; k < pulses.length; k++) {
        const q = pulses[k];
        q.u += (dt * PULSE_SPEED) / elen[q.e];
        if (q.u >= 1) {
          const to = q.dir === 1 ? eb[q.e] : ea[q.e];
          heat[to] = Math.min(1.3, heat[to] + q.amp * 0.9);
          spread(to, q.amp, q.e);
          continue;
        }
        const g = Math.sin(q.u * Math.PI) * Math.min(1, q.amp * 1.4);
        if (g > glow[q.e]) {
          glow[q.e] = g;
          lit.add(q.e);
        }
        edgePoint(q.e, q.dir === 1 ? q.u : 1 - q.u, pp, w * 3);
        pa[w] = 0.35 + Math.min(0.55, q.amp * 0.7);
        pulses[w++] = q;
      }
      pulses.length = w;
      pulseGeo.setDrawRange(0, w);
      pulseGeo.attributes.position.needsUpdate = true;
      pulseGeo.attributes.aAlpha.needsUpdate = true;

      if (flows.length) {
        const fp = flowGeo.attributes.position.array;
        const fa = flowGeo.attributes.aAlpha.array;
        for (let k = 0; k < flows.length; k++) {
          const f = flows[k];
          f.u += dt * f.rate;
          if (f.u >= 1) f.u -= 1;
          edgePoint(f.e, f.u, fp, k * 3);
          fa[k] = grow[f.e] < 1 ? 0 : 0.5 * Math.pow(Math.sin(f.u * Math.PI), 0.6);
        }
        flowGeo.setDrawRange(0, flows.length);
        flowGeo.attributes.position.needsUpdate = true;
        flowGeo.attributes.aAlpha.needsUpdate = true;
      }

      for (const e of growing) {
        grow[e] = Math.min(1, grow[e] + dt / EDGE_IN);
        writeEdge(e);
        if (grow[e] >= 1) growing.delete(e);
      }

      if (lit.size) {
        const gd = Math.exp(-dt * 3.5);
        for (const e of lit) {
          glow[e] *= gd;
          writeEdgeColor(e);
          if (glow[e] < 0.003 && grow[e] >= 1) {
            glow[e] = 0;
            writeEdgeColor(e);
            lit.delete(e);
          }
        }
      }

      if (moving.size) {
        const np = nodeGeo.attributes.position.array;
        const dirty = new Set();
        for (const i of moving) {
          const tg = pullT.get(i);
          let rest = true;
          for (let q = 0; q < 3; q++) {
            const k = i * 3 + q;
            const acc = 70 * ((tg ? tg[q] : 0) - disp[k]) - 7 * dvel[k];
            dvel[k] += acc * dt;
            disp[k] += dvel[k] * dt;
            pos[k] = np[k] = base[k] + disp[k];
            if (Math.abs(disp[k]) > 1e-4 || Math.abs(dvel[k]) > 1e-4) rest = false;
          }
          if (!tg && rest) {
            moving.delete(i);
            for (let q = 0; q < 3; q++) disp[i * 3 + q] = dvel[i * 3 + q] = 0, pos[i * 3 + q] = np[i * 3 + q] = base[i * 3 + q];
          }
          for (const e of adj[i]) dirty.add(e);
        }
        pullT.clear();
        for (const e of dirty) writeEdge(e);
        nodeGeo.attributes.position.needsUpdate = true;
      }

      nodeGeo.attributes.aHeat.array.set(heat.subarray(0, n));
      nodeGeo.attributes.aHeat.needsUpdate = true;

      if (posDirty) flushChunks(lineGeo.attributes.position, posChunks), (posDirty = false);
      if (colDirty) flushChunks(lineGeo.attributes.color, colChunks), (colDirty = false);
      for (const a of Object.values(nodeGeo.attributes)) {
        a.clearUpdateRanges();
        a.addUpdateRange(0, n * a.itemSize);
      }
    },
  };
  return api;
}
