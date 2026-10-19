import * as THREE from 'three';
import { createCosmos } from './cosmos.js';
import { createSpider } from './spider.js';
import { createSky } from './sky.js';
import { checkAnalyzer, streamProject, uploadProject, cloneGithub, getTree, analyzeProject, openSaved, updateSaved, importGraph, listSaved } from './project.js';
import { createWeaver } from './weaver.js';
import { createNest } from './nest.js';
import { clamp, damp, smooth, mulberry32 } from './rand.js';
import { toast } from './toast.js';
import { load, save, forget } from './storage.js';
import { createRecorder, saveBlob } from './recorder.js';
import { createCommunities } from './communities.js';

const canvas = document.querySelector('#stage');
const statusEl = document.querySelector('#status');
const hintEl = document.querySelector('#hint');
const labelsEl = document.querySelector('#labels');
const followBtn = document.querySelector('#follow');
const projectEl = document.querySelector('#project');
const chipsEl = document.querySelector('#chips');
const progressEl = document.querySelector('#progress');
const chip = {
  files: document.querySelector('#chip-files'),
  nodes: document.querySelector('#chip-nodes'),
  edges: document.querySelector('#chip-edges'),
  comms: document.querySelector('#chip-comms'),
  here: document.querySelector('#chip-here'),
};
const tipEl = document.querySelector('#tip');
const findBtn = document.querySelector('#find');
const searchEl = document.querySelector('#search');
const searchInput = document.querySelector('#search input');
const resultsEl = document.querySelector('#results');
const uploadBtn = document.querySelector('#upload');
const uploaderEl = document.querySelector('#uploader');
const uploadStatus = document.querySelector('#upload-status');
const openLastBtn = document.querySelector('#open-last');
const githubForm = document.querySelector('#github');
const exportBtn = document.querySelector('#export');
const exporterEl = document.querySelector('#exporter');
const speedBtn = document.querySelector('#speed');
const settingsEl = document.querySelector('#settings');
const recordBtn = document.querySelector('#record');
const recChip = document.querySelector('#rec-chip');
const recTime = document.querySelector('#rec-time');
const recCineBox = document.querySelector('#rec-cine');
const cineBtn = document.querySelector('#cine');
const cineHint = document.querySelector('#cine-hint');
const helpBtn = document.querySelector('#help-btn');
const helpEl = document.querySelector('#help');
const commsChip = document.querySelector('#comms-chip');
const commsEl = document.querySelector('#comms');
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
} catch (err) {
  throw new Error(`webgl: ${err?.message || err}`);
}
renderer.setClearColor(0x020309, 1);
let pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
renderer.setPixelRatio(pixelRatio);

const scene = new THREE.Scene();
const FOG = 0.028;
scene.fog = new THREE.FogExp2(0x000000, FOG);
const camera = new THREE.PerspectiveCamera(50, 1, 0.05, 900);

const sky = createSky(scene);
const cosmos = createCosmos(scene);
const spider = createSpider(scene, cosmos);
const nest = createNest(scene, cosmos.centers[0]);
const materials = [...sky.materials, ...cosmos.materials, ...spider.materials, ...nest.materials];
const rng = mulberry32(Date.now() & 0xffff);

const WALK = 1.5;
const TRAVEL = 4.8;
const BASE_R = 11;

const linksOf = (r) => cosmos.links.filter((L) => L.a === r || L.b === r);

function route(from, to) {
  const prev = new Map([[from, null]]);
  const queue = [from];
  while (queue.length) {
    const r = queue.shift();
    if (r === to) break;
    for (const L of linksOf(r)) {
      const n = L.a === r ? L.b : L.a;
      if (!prev.has(n)) prev.set(n, { r, L }), queue.push(n);
    }
  }
  const hops = [];
  for (let r = to; prev.get(r); r = prev.get(r).r) hops.unshift({ to: r, L: prev.get(r).L });
  return hops;
}

const brain = {
  mode: 'wander',
  region: 0,
  goal: new THREE.Vector3(),
  speed: WALK,
  maxSpeed: WALK,
  timer: 0,
  autopilot: 14 + rng() * 8,
  hops: [],
  seg: null,
  focus: -1,
  jumpTo: -1,
  pending: null,
  moved: 0,
};

const project = { name: '', active: false, done: false, woven: 0, current: '', reconnecting: false, fullWarned: false };

const nodeVec = (i, out = new THREE.Vector3()) => out.set(cosmos.pos[i * 3], cosmos.pos[i * 3 + 1], cosmos.pos[i * 3 + 2]);

function pickWander() {
  const list = cosmos.regionNodes[brain.region];
  const c = cosmos.centers[brain.region];
  brain.timer = 4 + rng() * 4;
  if (!list.length) {
    brain.goal.copy(c);
    return;
  }
  const n = brain.focus >= 0 ? brain.focus : list[Math.floor(rng() * list.length)];
  brain.focus = -1;
  const R = cosmos.regions[brain.region].nr;
  nodeVec(n, brain.goal);
  if (brain.goal.distanceTo(c) > R * 1.2) brain.goal.lerp(c, 0.4);
  brain.goal.y += 0.45;
}

function arrive() {
  spider.releaseSilk();
  brain.mode = 'wander';
  brain.speed = WALK;
  pickWander();
  setStatus(`explorando · ${cosmos.regions[brain.region].name}`);
  if (brain.pending) {
    const p = brain.pending;
    brain.pending = null;
    travelTo(p.r, p.focus);
  }
}

function nextHop() {
  const hop = brain.hops.shift();
  if (!hop) return arrive();
  const A = spider.pos.clone();
  const B = cosmos.centers[hop.to].clone();
  const C = hop.L.ctrl.clone().lerp(A.clone().add(B).multiplyScalar(0.5), 0.3);
  const len = A.distanceTo(C) + C.distanceTo(B);
  brain.seg = { A, B, C, len, s: 0, to: hop.to };
}

function jumpTo(r) {
  const list = cosmos.regionNodes[r];
  const v = new THREE.Vector3();
  let target = cosmos.centers[r].clone();
  if (list.length) {
    let best = list[0];
    let bd = Infinity;
    for (let k = 0; k < 40; k++) {
      const n = list[Math.floor(rng() * list.length)];
      const d = nodeVec(n, v).distanceTo(spider.pos) + rng() * 2;
      if (d < bd) (bd = d), (best = n);
    }
    target = nodeVec(best).lerp(cosmos.centers[r], 0.35);
  }
  brain.mode = 'jump';
  brain.jumpTo = r;
  spider.dropSilk();
  spider.jump(target);
  setStatus(`saltando → ${cosmos.regions[r].name}`);
}

function travelTo(r, focus = -1) {
  if (brain.mode === 'weave') {
    setStatus('la araña está tejiendo · espera a que termine', 2);
    toast('la araña está tejiendo · espera a que termine');
    return;
  }
  brain.autopilot = 22 + rng() * 18;
  brain.moved = 0;
  if (brain.mode === 'jump') {
    if (r !== brain.jumpTo || focus >= 0) brain.pending = { r, focus };
    return;
  }
  brain.focus = focus;
  if (brain.mode === 'travel') {
    brain.hops = route(brain.seg.to, r);
    setStatus(`viajando → ${cosmos.regions[r].name}`);
    return;
  }
  if (r === brain.region) {
    brain.mode = 'wander';
    brain.speed = WALK;
    pickWander();
    return;
  }
  const linked = linksOf(brain.region).some((L) => L.a === r || L.b === r);
  if (!linked || rng() < 0.45) return jumpTo(r);
  brain.hops = route(brain.region, r);
  spider.dropSilk();
  brain.mode = 'travel';
  brain.speed = TRAVEL;
  nextHop();
  setStatus(`viajando → ${cosmos.regions[r].name}`);
}

function think(dt) {
  if (brain.mode === 'weave') {
    brain.goal.copy(spider.pos);
    if (weaver && weaver.done && !spider.airborne) arrive();
    return;
  }
  if (brain.mode === 'jump') {
    brain.goal.copy(spider.pos);
    if (!spider.airborne) {
      brain.region = brain.jumpTo;
      brain.jumpTo = -1;
      brain.maxSpeed = 0;
      arrive();
    }
  } else if (brain.mode === 'travel') {
    const g = brain.seg;
    g.s = Math.min(1, g.s + (dt * brain.maxSpeed * 0.95) / g.len);
    const t = g.s, u = 1 - t;
    brain.goal.set(
      u * u * g.A.x + 2 * u * t * g.C.x + t * t * g.B.x,
      u * u * g.A.y + 2 * u * t * g.C.y + t * t * g.B.y,
      u * u * g.A.z + 2 * u * t * g.C.z + t * t * g.B.z
    );
    if (g.s >= 1 && spider.pos.distanceTo(g.B) < 1.2) {
      brain.region = g.to;
      nextHop();
    }
  } else {
    brain.timer -= dt;
    const arrived = spider.pos.distanceTo(brain.goal) < 0.3;
    if (brain.mode === 'rest' && brain.timer <= 0) {
      brain.mode = 'wander';
      brain.speed = WALK;
      pickWander();
    } else if (brain.mode === 'wander' && (arrived || brain.timer <= 0)) {
      if (rng() < 0.3) {
        brain.mode = 'rest';
        brain.speed = 0;
        brain.timer = 1.5 + rng() * 2.5;
      } else pickWander();
    }
    brain.moved += dt;
    brain.autopilot -= dt;
    if (brain.autopilot <= 0 && (!project.active || project.done) && cosmos.regions.length > 1) {
      const others = cosmos.regions.map((_, i) => i).filter((i) => i !== brain.region);
      travelTo(others[Math.floor(rng() * others.length)]);
    }
  }
  brain.maxSpeed += (brain.speed - brain.maxSpeed) * damp(1.5, dt);
}

const cam = {
  theta: 0.9,
  phi: 1.15,
  r: 50,
  rGoal: BASE_R,
  boost: 0,
  target: new THREE.Vector3(),
  follow: true,
  vTheta: 0,
  vPhi: 0,
  vPan: new THREE.Vector3(),
  refocus: 0,
  manualAt: -10,
  intro: 0,
};
const camPos = new THREE.Vector3();
const camRight = new THREE.Vector3();
const camUp = new THREE.Vector3();
const keys = new Set();
const MIN_R = 2.5;
const MAX_R = 450;

function panBy(dx, dy) {
  const k = (2 * cam.r * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) / (canvas.clientHeight || 1);
  camRight.setFromMatrixColumn(camera.matrixWorld, 0);
  camUp.setFromMatrixColumn(camera.matrixWorld, 1);
  const d = camRight.multiplyScalar(-dx * k).addScaledVector(camUp, dy * k);
  cam.target.add(d);
  return d;
}

function updateCamera(dt) {
  if (cam.follow) {
    cam.refocus = Math.max(0, cam.refocus - dt);
    const rate = cam.refocus > 0 ? 6 : spider.flying ? 7 : 3.5;
    cam.target.lerp(spider.pos, damp(rate, dt));
    if (time - cam.manualAt > 3 && !dragMode) {
      const f = spider.fwd;
      if (f.x * f.x + f.z * f.z > 0.02) {
        const want = Math.atan2(-f.x, -f.z) + 0.65;
        let d = want - cam.theta;
        d = Math.atan2(Math.sin(d), Math.cos(d));
        cam.theta += d * damp(cam.refocus > 0 ? 2.5 : 0.9, dt);
      }
      cam.phi += (1.08 - cam.phi) * damp(0.7, dt);
    }
  }
  if (dragMode !== 'orbit') {
    cam.theta += cam.vTheta;
    cam.phi = clamp(cam.phi + cam.vPhi, 0.15, Math.PI - 0.15);
    cam.vTheta *= Math.exp(-dt * 4);
    cam.vPhi *= Math.exp(-dt * 4);
  }
  if (dragMode !== 'pan') {
    cam.target.add(cam.vPan);
    cam.vPan.multiplyScalar(Math.exp(-dt * 5));
  }
  if (keys.size) {
    const s = cam.r * 0.9 * dt;
    let kx = 0, ky = 0;
    if (keys.has('a') || keys.has('arrowleft')) kx -= 1;
    if (keys.has('d') || keys.has('arrowright')) kx += 1;
    if (keys.has('w') || keys.has('arrowup') || keys.has('e')) ky += 1;
    if (keys.has('s') || keys.has('arrowdown') || keys.has('q')) ky -= 1;
    if (kx || ky) {
      if (cam.follow) setFollow(false);
      camRight.setFromMatrixColumn(camera.matrixWorld, 0);
      camUp.setFromMatrixColumn(camera.matrixWorld, 1);
      cam.target.addScaledVector(camRight, kx * s).addScaledVector(camUp, ky * s);
    }
  }
  if (!dragMode && !reduced && !cam.follow) cam.theta += dt * 0.025;
  cam.intro = Math.min(1, cam.intro + dt / 5);
  cam.boost += ((spider.flying && cam.follow ? 7 : 0) - cam.boost) * damp(1.5, dt);
  const k = cam.intro < 1 ? smooth(cam.intro) * 0.06 + 0.012 : damp(4, dt);
  cam.r += (cam.rGoal - cam.r) * k;
  const r = cam.r + cam.boost;
  camPos.set(
    Math.sin(cam.phi) * Math.sin(cam.theta),
    Math.cos(cam.phi),
    Math.sin(cam.phi) * Math.cos(cam.theta)
  ).multiplyScalar(r).add(cam.target);
  camera.position.copy(camPos);
  camera.lookAt(cam.target);
  camera.updateMatrixWorld();

  const fk = BASE_R / Math.max(BASE_R, r);
  for (const m of materials) m.uniforms.uFog.value = m.userData.fog0 * fk * fk;
  scene.fog.density = FOG * fk;
  const far = clamp((r - 14) / 70, 0, 1) * (project.active ? 0.6 : 1.3);
  for (const m of cosmos.boostMaterials) m.uniforms.uBoost.value = 1 + far;
  for (const m of cosmos.lineMaterials) m.color.setScalar(1 + far * (project.active ? 0.5 : 1));
}

let statusTimer = 0;
function setStatus(text, hold = 0) {
  if (statusTimer > 0 && !hold) return;
  statusEl.textContent = text;
  statusTimer = hold;
}

let hinted = false;
function interacted() {
  if (hinted) return;
  hinted = true;
  hintEl.classList.add('gone');
}

const labels = [];
const fmt = (n) => n.toLocaleString('es');
const rgb = (c) => `rgb(${c.map((x) => Math.round(x * 255)).join(' ')})`;
const escapeHtml = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

function ensureLabels() {
  for (let i = labels.length; i < cosmos.regions.length; i++) {
    const R = cosmos.regions[i];
    if (i > 0) nest.addThread(i, cosmos.centers[i], R.nr, R.color);
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'label';
    b.style.setProperty('--c', rgb(R.color));
    const sub = R.sub && R.sub !== R.name ? `<small>${escapeHtml(R.sub)}</small>` : '';
    b.innerHTML = `<span class="dot"></span><span class="name">${escapeHtml(R.name)}${sub}</span>`;
    b.addEventListener('click', () => {
      interacted();
      travelTo(i);
    });
    labelsEl.appendChild(b);
    labels.push(b);
  }
}
const anchor = new THREE.Vector3();

function updateLabels() {
  ensureLabels();
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const going = new Set(brain.mode === 'travel' ? brain.hops.map((x) => x.to).concat(brain.seg ? [brain.seg.to] : []) : []);
  if (brain.mode === 'jump') going.add(brain.jumpTo);
  const placed = [];
  const order = cosmos.regions.map((_, i) => i).sort((a, b) => cosmos.centers[a].distanceToSquared(camera.position) - cosmos.centers[b].distanceToSquared(camera.position));
  for (const i of order) {
    const R = cosmos.regions[i];
    anchor.copy(cosmos.centers[i]);
    anchor.y += R.nr * 0.95;
    const d = anchor.distanceTo(camera.position);
    anchor.project(camera);
    const el = labels[i];
    const sx = (anchor.x * 0.5 + 0.5) * w, sy = (-anchor.y * 0.5 + 0.5) * h;
    const crowded = placed.some((p) => Math.abs(p[0] - sx) < 175 && Math.abs(p[1] - sy) < 54);
    if (anchor.z > 1 || Math.abs(anchor.x) > 1.1 || Math.abs(anchor.y) > 1.1 || crowded || sy < 96) {
      el.style.opacity = 0;
      el.style.pointerEvents = 'none';
      continue;
    }
    placed.push([sx, sy]);
    const near = clamp((d - 3) / 6, 0, 1);
    const far = clamp(1 - (d - 70) / 90, 0.6, 1);
    const op = near * far;
    el.style.opacity = op.toFixed(3);
    el.style.pointerEvents = op > 0.2 ? 'auto' : 'none';
    el.style.transform = `translate(${sx.toFixed(1)}px, ${sy.toFixed(1)}px) translate(-50%, -100%)`;
    el.classList.toggle('here', brain.region === i && brain.mode !== 'travel' && brain.mode !== 'jump');
    el.classList.toggle('going', going.has(i));
  }
}

function setFollow(on) {
  cam.follow = on;
  followBtn.setAttribute('aria-pressed', String(on));
  if (on) {
    cam.refocus = 1.6;
    cam.vPan.set(0, 0, 0);
    keys.clear();
    cam.rGoal = clamp(cam.rGoal, 5, 22);
  }
  setStatus(on ? 'enfocando a la araña' : 'cámara libre', 1.8);
}
followBtn.addEventListener('click', () => {
  interacted();
  setFollow(true);
});

const pointers = new Map();
let dragMode = null;
let moved = 0;
let pinch = 0;
let downAt = 0;
let mid = null;

const viewProj = new THREE.Matrix4();
function pickNode(x, y, radius = 30) {
  const rect = canvas.getBoundingClientRect();
  const m = viewProj.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).elements;
  const P = cosmos.pos;
  const hw = rect.width / 2, hh = rect.height / 2;
  const tx = x - rect.left, ty = y - rect.top;
  let best = -1;
  let bd = radius * radius;
  for (let i = 0, n = cosmos.count; i < n; i++) {
    const px = P[i * 3], py = P[i * 3 + 1], pz = P[i * 3 + 2];
    const w = m[3] * px + m[7] * py + m[11] * pz + m[15];
    if (w <= 0.05) continue;
    const sx = ((m[0] * px + m[4] * py + m[8] * pz + m[12]) / w + 1) * hw;
    const sy = (1 - (m[1] * px + m[5] * py + m[9] * pz + m[13]) / w) * hh;
    const d = (sx - tx) ** 2 + (sy - ty) ** 2;
    if (d < bd) (bd = d), (best = i);
  }
  return best;
}

const midpoint = () => {
  const [a, b] = [...pointers.values()];
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, d: Math.hypot(a.x - b.x, a.y - b.y) };
};

canvas.addEventListener('contextmenu', (e) => e.preventDefault());
canvas.addEventListener('pointerdown', (e) => {
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  canvas.setPointerCapture(e.pointerId);
  if (pointers.size === 2) {
    mid = midpoint();
    pinch = mid.d;
    dragMode = 'touch2';
    moved = 99;
    return;
  }
  dragMode = e.button === 2 || e.button === 1 || e.shiftKey ? 'pan' : 'orbit';
  hideTip();
  closePopovers();
  moved = 0;
  downAt = performance.now();
  cam.vTheta = cam.vPhi = 0;
  cam.vPan.set(0, 0, 0);
});
canvas.addEventListener('pointermove', (e) => {
  const p = pointers.get(e.pointerId);
  if (!p) return hover(e);
  const dx = e.clientX - p.x, dy = e.clientY - p.y;
  p.x = e.clientX;
  p.y = e.clientY;
  if (dragMode === 'touch2' && pointers.size >= 2) {
    const m = midpoint();
    if (pinch > 0) cam.rGoal = clamp((cam.rGoal * pinch) / Math.max(8, m.d), MIN_R, MAX_R);
    if (mid) {
      const mx = m.x - mid.x, my = m.y - mid.y;
      if (Math.abs(mx) + Math.abs(my) > 0.5) {
        if (cam.follow) setFollow(false);
        panBy(mx, my);
      }
    }
    pinch = m.d;
    mid = m;
    userZoomed = true;
    interacted();
    return;
  }
  if (!dragMode) return;
  moved += Math.abs(dx) + Math.abs(dy);
  if (moved > 6) interacted();
  if (dragMode === 'pan') {
    if (moved > 3 && cam.follow) setFollow(false);
    cam.vPan.copy(panBy(dx, dy));
    return;
  }
  cam.manualAt = time;
  cam.vTheta = -dx * 0.005;
  cam.vPhi = -dy * 0.004;
  cam.theta += cam.vTheta;
  cam.phi = clamp(cam.phi + cam.vPhi, 0.15, Math.PI - 0.15);
});
const release = (e) => {
  pointers.delete(e.pointerId);
  if (pointers.size < 2) pinch = 0, (mid = null);
  if (pointers.size > 0) {
    if (dragMode === 'touch2') (dragMode = 'orbit'), (moved = 99);
    return;
  }
  const wasTap = dragMode === 'orbit' && moved < 7 && performance.now() - downAt < 450 && e.button === 0;
  dragMode = null;
  if (!wasTap) return;
  const n = pickNode(e.clientX, e.clientY);
  if (n < 0) return;
  interacted();
  cosmos.fire(n, 1.1);
  let r = cosmos.nodeRegion[n];
  if (r < 0) r = cosmos.regionAt(nodeVec(n));
  if (r >= 0) {
    travelTo(r, cosmos.nodeRegion[n] === r ? n : -1);
    if (brain.mode !== 'travel' && brain.mode !== 'jump') setStatus(`impulso en ${cosmos.regions[r].name}`, 2);
  }
};
canvas.addEventListener('pointerup', release);
canvas.addEventListener('pointercancel', release);
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  const d = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;
  cam.rGoal = clamp(cam.rGoal * Math.exp(clamp(d, -240, 240) * 0.0014), MIN_R, MAX_R);
  cam.intro = 1;
  userZoomed = true;
  hideTip();
  interacted();
}, { passive: false });
window.addEventListener('keydown', (e) => {
  if (e.target.closest?.('input, textarea, select')) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === 'escape') return escape();
  if (e.key === '?') {
    e.preventDefault();
    return openHelp(helpEl.hidden);
  }
  if (!helpEl.hidden) return;
  if (k === 'h') return setCine(!cine.on);
  if (k === 'f') return setFollow(true);
  if (k === '/' && project.active) {
    e.preventDefault();
    return openSearch(true);
  }
  if (['w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright'].includes(k)) {
    e.preventDefault();
    keys.add(k);
    interacted();
  }
});
window.addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));
window.addEventListener('blur', () => keys.clear());

let userZoomed = false;
function resize() {
  const w = canvas.clientWidth || 1, h = canvas.clientHeight || 1;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  const px = (h * renderer.getPixelRatio()) / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
  for (const m of materials) m.uniforms.uPx.value = px;
  if (!userZoomed) cam.rGoal = BASE_R * (1 + clamp(1 - camera.aspect, 0, 0.6) * 0.9);
}
new ResizeObserver(resize).observe(canvas);
resize();

spider.place(nodeVec(cosmos.regionNodes[0][0]));
pickWander();
setStatus('en el nido');

const KIND_NAME = { module: 'archivo', doc: 'documento', class: 'clase', function: 'función', method: 'método' };
const tip = { node: -1, x: 0, y: 0, timer: 0, last: null };
function hideTip() {
  tipEl.hidden = true;
  tip.node = -1;
  cosmos.graph.setHot(-1);
}
function hover(e) {
  tip.last = { clientX: e.clientX, clientY: e.clientY };
  if (tip.node >= 0 && Math.hypot(e.clientX - tip.x, e.clientY - tip.y) > 20) hideTip();
  if (!tip.timer) tip.timer = setTimeout(() => {
    tip.timer = 0;
    if (!pointers.size && tip.last) showTip(tip.last);
  }, 60);
}
function showTip(e) {
  const n = pickNode(e.clientX, e.clientY, 14);
  const m = n >= 0 ? cosmos.meta[n] : null;
  if (!m) return hideTip();
  tip.node = n;
  tip.x = e.clientX;
  tip.y = e.clientY;
  cosmos.graph.setHot(n);
  cosmos.hold(n, 1);
  const R = cosmos.regions[m.region];
  tipEl.innerHTML = `<b>${escapeHtml(m.name)}</b>
    <span>${KIND_NAME[m.kind] || m.kind} · ${escapeHtml(m.file)}${m.line > 1 ? `:${m.line}` : ''}</span>
    ${m.route ? `<span class="tag">${escapeHtml(m.route)}</span>` : ''}${m.table ? `<span class="tag">tabla ${escapeHtml(m.table)}</span>` : ''}
    <span>${escapeHtml(R.name)} · ${m.deg} conexiones</span>`;
  tipEl.style.setProperty('--c', rgb(R.color));
  const x = Math.min(e.clientX + 16, window.innerWidth - 300);
  const y = Math.min(e.clientY + 16, window.innerHeight - 110);
  tipEl.style.transform = `translate(${x}px, ${y}px)`;
  tipEl.hidden = false;
}
canvas.addEventListener('pointerleave', () => {
  tip.last = null;
  hideTip();
});
const tipProj = new THREE.Vector3();
function checkTip() {
  if (tip.node < 0) return;
  const rect = canvas.getBoundingClientRect();
  nodeVec(tip.node, tipProj).project(camera);
  const sx = (tipProj.x * 0.5 + 0.5) * rect.width + rect.left, sy = (-tipProj.y * 0.5 + 0.5) * rect.height + rect.top;
  if (tipProj.z > 1 || Math.hypot(sx - tip.x, sy - tip.y) > 24) hideTip();
}

window.addEventListener('contextmenu', (e) => {
  if (!e.target.closest?.('input, textarea')) e.preventDefault();
});
document.addEventListener('selectstart', (e) => {
  if (!e.target.closest?.('input, textarea')) e.preventDefault();
});

const FALLBACK_FORMATS = {
  exts: ['.py', '.ipynb', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.md', '.go', '.rs', '.java', '.kt', '.cs', '.php', '.rb', '.c', '.h', '.cpp', '.swift', '.yml', '.yaml', '.toml', '.json', '.sql'],
  names: ['Dockerfile', 'Makefile'], prefixes: ['Dockerfile.', 'docker-compose'],
  skip_dirs: ['node_modules', '.git', '.next', '__pycache__', '.venv', 'venv', 'dist', 'build', 'vendor', 'target'],
  skip_suffixes: ['.min.js', '.map', '.d.ts'], locks: ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml'],
  max_bytes: 2 * 1024 * 1024, max_notebook_bytes: 40 * 1024 * 1024,
};
let formatsPromise = null;
function loadFormats() {
  formatsPromise ||= fetch('/api/formatos').then((r) => (r.ok ? r.json() : FALLBACK_FORMATS)).catch(() => FALLBACK_FORMATS);
  return formatsPromise;
}
function fileFilter(fm) {
  const exts = new Set(fm.exts);
  const names = new Set(fm.names);
  const locks = new Set(fm.locks);
  const skipDirs = new Set(fm.skip_dirs);
  return (f) => {
    const parts = f.webkitRelativePath.split('/');
    const name = parts[parts.length - 1];
    if (parts.slice(0, -1).some((p) => skipDirs.has(p)) || locks.has(name) || name.startsWith('.env')) return false;
    if (fm.skip_suffixes.some((s) => name.endsWith(s))) return false;
    const dot = name.lastIndexOf('.');
    const ext = dot > 0 ? name.slice(dot) : '';
    if (!name.includes('.') && !names.has(name) && name !== name.toUpperCase()) return f.size <= (fm.max_script_bytes || 262144);
    if (!(exts.has(ext) || names.has(name) || fm.prefixes.some((p) => name.startsWith(p)))) return false;
    return f.size <= (ext === '.ipynb' ? fm.max_notebook_bytes : fm.max_bytes);
  };
}
const OPEN_FLAG = 'cortex-abrir';
const popovers = [];
function popover(el, btn, onOpen) {
  const entry = { el };
  entry.toggle = (open) => {
    if (open) closePopovers(el);
    el.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
    if (open && onOpen) onOpen();
  };
  popovers.push(entry);
  return entry.toggle;
}
function closePopovers(except) {
  for (const p of popovers) if (p.el !== except && !p.el.hidden) p.toggle(false);
}
const openExporter = popover(exporterEl, exportBtn);
const openUploader = popover(uploaderEl, uploadBtn);
const openSettings = popover(settingsEl, speedBtn);
const openComms = popover(commsEl, commsChip, () => communities.render());
const openSearch = popover(searchEl, findBtn, () => {
  searchInput.value = '';
  resultsEl.innerHTML = '';
  searchInput.focus();
});
exportBtn.addEventListener('click', () => openExporter(exporterEl.hidden));
uploadBtn.addEventListener('click', () => openUploader(uploaderEl.hidden));
speedBtn.addEventListener('click', () => openSettings(settingsEl.hidden));
commsChip.addEventListener('click', () => openComms(commsEl.hidden));
findBtn.addEventListener('click', () => openSearch(searchEl.hidden));

function begin() {
  if (project.active) {
    save(OPEN_FLAG, '1', 'session');
    return location.reload();
  }
  openUploader(false);
  weave();
}
async function choose(job) {
  try {
    const out = await job();
    project.name = out.project;
    if (out.state === 'cloning') {
      uploadStatus.textContent = `clonando ${out.project}…`;
      for (;;) {
        await new Promise((r) => setTimeout(r, 1000));
        const st = await checkAnalyzer();
        if (!st || st.state === 'error') throw new Error(st?.error || 'se perdió la conexión con el analizador');
        if (st.state === 'review') break;
      }
    }
    uploadStatus.textContent = '';
    showReview();
  } catch (err) {
    fail(err);
  }
}

const reviewView = document.querySelector('#review-view');
const pickView = document.querySelector('#pick-view');
const treeEl = document.querySelector('#review-tree');
const testsBox = document.querySelector('#review-tests');
const reviewGo = document.querySelector('#review-go');
const review = { files: [], tests: new Set(), excluded: new Set() };

const excludedPath = (f) => {
  for (const p of review.excluded) if (f === p || f.startsWith(p + '/')) return true;
  return false;
};
function reviewCount() {
  const n = review.files.filter((f) => !excludedPath(f) && (testsBox.checked || !review.tests.has(f))).length;
  reviewGo.textContent = `Tejer ${fmt(n)} archivos`;
  reviewGo.disabled = n === 0;
}
function buildTree(files) {
  const root = { name: '', path: '', dirs: new Map(), files: [], total: 0, tests: 0 };
  for (const f of files) {
    const parts = f.split('/');
    let node = root;
    node.total++;
    if (review.tests.has(f)) node.tests++;
    for (let i = 0; i < parts.length - 1; i++) {
      const path = parts.slice(0, i + 1).join('/');
      if (!node.dirs.has(parts[i])) node.dirs.set(parts[i], { name: parts[i], path, dirs: new Map(), files: [], total: 0, tests: 0 });
      node = node.dirs.get(parts[i]);
      node.total++;
      if (review.tests.has(f)) node.tests++;
    }
    node.files.push(f);
  }
  return root;
}
function renderDir(node, ul) {
  const dirs = [...node.dirs.values()].sort((a, b) => a.name.localeCompare(b.name));
  for (const d of dirs) {
    const li = document.createElement('li');
    const det = document.createElement('details');
    const sum = document.createElement('summary');
    const onlyTests = d.tests === d.total;
    sum.innerHTML = `<span class="row-item"><span class="caret">▸</span><input type="checkbox" data-path="${escapeHtml(d.path)}" ${excludedPath(d.path) ? '' : 'checked'} /><span>${escapeHtml(d.name)}/</span>${onlyTests ? '<span class="tag">tests</span>' : ''}<span class="count">${fmt(d.total)}</span></span>`;
    det.appendChild(sum);
    const sub = document.createElement('ul');
    det.appendChild(sub);
    det.addEventListener('toggle', () => {
      if (det.open && !sub.childElementCount) renderDir(d, sub);
    });
    li.appendChild(det);
    ul.appendChild(li);
  }
  for (const f of node.files.sort()) {
    const li = document.createElement('li');
    const isTest = review.tests.has(f);
    li.innerHTML = `<label class="row-item${isTest && !testsBox.checked ? ' off' : ''}"><span class="caret"></span><input type="checkbox" data-path="${escapeHtml(f)}" ${excludedPath(f) ? '' : 'checked'} /><span>${escapeHtml(f.split('/').pop())}</span>${isTest ? '<span class="tag">test</span>' : ''}</label>`;
    ul.appendChild(li);
  }
}
treeEl.addEventListener('click', (e) => {
  if (e.target.matches('input[type=checkbox]')) e.stopPropagation();
});
treeEl.addEventListener('change', (e) => {
  const box = e.target;
  if (!box.matches('input[type=checkbox]')) return;
  const path = box.dataset.path;
  if (box.checked) review.excluded.delete(path);
  else review.excluded.add(path);
  box.closest('li').querySelectorAll('ul input[type=checkbox]').forEach((c) => {
    c.checked = box.checked;
    if (box.checked) review.excluded.delete(c.dataset.path);
  });
  reviewCount();
});
testsBox.addEventListener('change', () => {
  treeEl.querySelectorAll('.row-item').forEach((row) => {
    if (row.querySelector('.tag')?.textContent === 'test') row.classList.toggle('off', !testsBox.checked);
  });
  reviewCount();
});
async function showReview() {
  try {
    const t = await getTree();
    project.name = t.project;
    review.files = t.files;
    review.tests = new Set(t.tests);
    review.excluded = new Set();
    testsBox.checked = false;
    document.querySelector('#review-tests-label').textContent = `Incluir tests (${fmt(t.tests.length)} archivos)`;
    const top = [...new Set(t.files.map((f) => (f.includes('/') ? f.split('/')[0] : null)).filter(Boolean))];
    document.querySelector('#review-summary').textContent = `${t.project} · ${fmt(t.files.length)} archivos en ${fmt(top.length)} carpetas. Desmarca lo que no quieras procesar.`;
    treeEl.innerHTML = '';
    renderDir(buildTree(t.files), treeEl);
    pickView.hidden = true;
    reviewView.hidden = false;
    openUploader(true);
    reviewCount();
  } catch (err) {
    fail(err);
  }
}
document.querySelector('#review-cancel').addEventListener('click', () => {
  reviewView.hidden = true;
  pickView.hidden = false;
});
reviewGo.addEventListener('click', async () => {
  reviewGo.disabled = true;
  try {
    await analyzeProject({ exclude: [...review.excluded], tests: testsBox.checked });
    reviewView.hidden = true;
    pickView.hidden = false;
    begin();
  } catch (err) {
    fail(err);
    reviewGo.disabled = false;
  }
});
document.querySelector('#pick-folder').addEventListener('change', async (e) => {
  const files = [...e.target.files];
  e.target.value = '';
  if (!files.length) return;
  const root = files[0].webkitRelativePath.split('/')[0] || 'proyecto';
  uploadStatus.textContent = 'revisando la carpeta…';
  const keep = files.filter(fileFilter(await loadFormats()));
  if (!keep.length) return (uploadStatus.textContent = 'esa carpeta no tiene código, configuración ni documentos para analizar');
  uploadStatus.textContent = `leyendo ${fmt(keep.length)} archivos…`;
  const lines = await Promise.all(keep.map(async (f) => JSON.stringify({ path: f.webkitRelativePath.split('/').slice(1).join('/'), content: await f.text() })));
  uploadStatus.textContent = 'subiendo…';
  choose(() => uploadProject(new Blob([lines.join('\n')], { type: 'application/x-ndjson' }), root));
});
document.querySelector('#pick-zip').addEventListener('change', (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  uploadStatus.textContent = 'subiendo…';
  choose(() => uploadProject(file, file.name.replace(/\.zip$/i, '')));
});
githubForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const url = githubForm.querySelector('input').value.trim();
  if (!url) return;
  uploadStatus.textContent = 'pidiendo el repo…';
  choose(() => cloneGithub(url));
});
openLastBtn.addEventListener('click', () => begin());

const savedEl = document.querySelector('#saved');
const savedList = document.querySelector('#saved-list');
const ago = (iso) => {
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (s < 3600) return `hace ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} d`;
};
async function waitReady() {
  for (;;) {
    const st = await checkAnalyzer();
    if (!st || st.state === 'error') throw new Error(st?.error || 'se perdió la conexión con el analizador');
    if (st.state === 'ready') return st;
    await new Promise((r) => setTimeout(r, 1000));
  }
}
async function renderSaved() {
  const list = await listSaved();
  savedEl.hidden = !list.length;
  savedList.innerHTML = '';
  for (const p of list) {
    const li = document.createElement('li');
    const ch = p.last.changes || {};
    const delta = p.versions > 1 ? ` · +${ch.added} ~${ch.modified} −${ch.removed}` : '';
    li.innerHTML = `<span class="info"><b>${escapeHtml(p.project)}</b><span>v${p.last.v} · ${fmt(p.last.stats.nodes)} nodos · ${ago(p.last.date)}${delta}</span></span>
      <button type="button" data-act="open">Abrir</button><button type="button" data-act="update">Actualizar</button>`;
    li.querySelector('[data-act=open]').addEventListener('click', async () => {
      uploadStatus.textContent = `abriendo ${p.project}…`;
      try {
        await openSaved(p.project);
        begin();
      } catch (err) {
        fail(err);
      }
    });
    li.querySelector('[data-act=update]').addEventListener('click', async () => {
      if (p.origin?.type !== 'github') {
        uploadStatus.textContent = `para actualizar ${p.project} vuelve a subir su carpeta o .zip: se compara con la v${p.last.v}`;
        return;
      }
      uploadStatus.textContent = `actualizando ${p.project} desde GitHub…`;
      try {
        await updateSaved(p.project);
        await waitReady();
        begin();
      } catch (err) {
        fail(err);
      }
    });
    savedList.appendChild(li);
  }
}
document.querySelector('#pick-import').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  uploadStatus.textContent = 'importando…';
  try {
    await importGraph(file);
    begin();
  } catch (err) {
    fail(err);
  }
});

function goToNode(n) {
  const r = cosmos.nodeRegion[n];
  if (r < 0) return;
  if (brain.mode === 'weave') return travelTo(r, n);
  travelTo(r, n);
  setFollow(true);
  cosmos.fire(n, 1.2);
  setStatus(`yendo a ${cosmos.meta[n]?.name || 'nodo'}`, 2.5);
}
searchInput.addEventListener('input', () => {
  const q = searchInput.value.trim().toLowerCase();
  resultsEl.innerHTML = '';
  if (q.length < 2) return;
  const hits = [];
  for (let i = 0; i < cosmos.meta.length && hits.length < 60; i++) {
    const m = cosmos.meta[i];
    if (!m) continue;
    const name = m.name.toLowerCase();
    if (name.includes(q) || m.file.toLowerCase().includes(q)) hits.push([i, name.startsWith(q) ? 0 : name.includes(q) ? 1 : 2, m.deg]);
  }
  hits.sort((a, b) => a[1] - b[1] || b[2] - a[2]);
  for (const [i] of hits.slice(0, 8)) {
    const m = cosmos.meta[i];
    const li = document.createElement('li');
    li.innerHTML = `<button type="button"><b>${escapeHtml(m.name)}</b><span>${KIND_NAME[m.kind] || m.kind} · ${escapeHtml(m.file)}</span></button>`;
    li.querySelector('button').addEventListener('click', () => {
      openSearch(false);
      goToNode(i);
    });
    resultsEl.appendChild(li);
  }
});
searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') openSearch(false);
  if (e.key === 'Enter') resultsEl.querySelector('button')?.click();
  e.stopPropagation();
});

const SPEEDS = [0.5, 1, 2, 4];
const SPEED_KEY = 'cortex-velocidad';
const CINE_KEY = 'cortex-cine-al-grabar';
const urlSpeed = Number(new URLSearchParams(location.search).get('velocidad'));
let weaveSpeed = urlSpeed > 0 ? urlSpeed : SPEEDS.includes(Number(load(SPEED_KEY))) ? Number(load(SPEED_KEY)) : 1;
let weaver = null;
let stream = null;

const speedLabel = (v) => `${v}×`;
function setSpeed(v, persist = true) {
  weaveSpeed = v;
  if (weaver) weaver.speed = v;
  speedBtn.textContent = speedLabel(v);
  settingsEl.querySelectorAll('[data-speed]').forEach((b) => b.setAttribute('aria-checked', String(Number(b.dataset.speed) === v)));
  if (persist) save(SPEED_KEY, v);
}
settingsEl.querySelectorAll('[data-speed]').forEach((b) =>
  b.addEventListener('click', () => {
    setSpeed(Number(b.dataset.speed));
    setStatus(`tejido a ${speedLabel(weaveSpeed)}`, 1.5);
  })
);
setSpeed(weaveSpeed, false);

function fail(err) {
  const text = String(err?.message || err || 'algo salió mal');
  uploadStatus.textContent = text;
  toast(text, { kind: 'error', ms: 5200 });
}

function weave() {
  project.active = true;
  findBtn.hidden = false;
  chipsEl.hidden = false;
  progressEl.hidden = false;
  projectEl.textContent = `${project.name || 'proyecto'} · conectando`;
  setFollow(true);
  if (!userZoomed) cam.rGoal = 14;
  weaver = createWeaver({
    cosmos,
    spider,
    speed: weaveSpeed,
    onHop(region, head, far) {
      nest.pulse(region);
      spider.beat();
      brain.mode = 'weave';
      brain.region = region;
      spider.dropSilk();
      project.current = head.file;
      setStatus(far ? `saltando a ${cosmos.regions[region].name}` : `tejiendo ${head.name}`);
    },
    onProgress(done, total, streamDone) {
      project.woven = done;
      const pct = (done / Math.max(1, total)) * 100;
      if (!project.reconnecting) projectEl.textContent = `${project.name} · tejiendo ${Math.round(pct)}%`;
      progressEl.firstElementChild.style.width = `${pct}%`;
      if (streamDone && done >= total) progressEl.hidden = true;
    },
  });
  brain.mode = 'weave';
  const finishWeaving = () => {
    weaver.finish();
    const wait = setInterval(() => {
      if (!weaver.done) return;
      clearInterval(wait);
      project.done = true;
      exportBtn.hidden = false;
      project.current = '';
      progressEl.hidden = true;
      projectEl.textContent = project.name;
    }, 300);
  };
  stream = streamProject({
    onWaiting(kind, name) {
      project.name = name;
      projectEl.textContent = `${name} · ${kind === 'cloning' ? 'clonando el repo…' : 'analizando el código…'}`;
    },
    onMeta(o) {
      project.name = o.project;
      const vEl = document.querySelector('#chip-version');
      const cEl = document.querySelector('#chip-changes');
      if (o.version) (vEl.hidden = false), (vEl.textContent = `v${o.version}`);
      const c = o.changes || {};
      if (o.version > 1 && (c.added || c.modified || c.removed)) {
        cEl.hidden = false;
        cEl.textContent = `+${fmt(c.added || 0)} nuevos · ${fmt(c.modified || 0)} modificados · ${fmt(c.removed || 0)} eliminados`;
      }
    },
    onItems(items) {
      weaver.push(items);
    },
    onReconnect(attempt, max) {
      project.reconnecting = true;
      projectEl.textContent = `${project.name || 'proyecto'} · reconectando…`;
      toast(`se cortó la conexión · reconectando… (${attempt}/${max})`, { kind: 'warn' });
    },
    onResumed() {
      project.reconnecting = false;
      toast('conexión recuperada · la araña sigue tejiendo');
    },
    onDone: finishWeaving,
    onError(err, info) {
      project.reconnecting = false;
      const text = String(err);
      if (info?.lost && stream?.received) {
        projectEl.textContent = `${project.name || 'proyecto'} · conexión perdida`;
        toast(`${text} · se teje lo que ya llegó`, { kind: 'error', ms: 6000 });
        finishWeaving();
        return;
      }
      projectEl.textContent = `${project.name || 'proyecto'} · ${text}`;
      brain.mode = 'wander';
      openUploader(true);
      fail(text);
    },
  });
}

checkAnalyzer().then((status) => {
  if (!status) {
    cosmos.seedDemo();
    setStatus('modo demostración');
    toast('sin analizador: se muestra una red de demostración');
    return;
  }
  uploadBtn.hidden = false;
  if (load(OPEN_FLAG, null, 'session')) {
    forget(OPEN_FLAG, 'session');
    project.name = status.project;
    return weave();
  }
  if (status.state === 'ready') exportBtn.hidden = false;
  if (status.state === 'review') return showReview();
  if (status.state === 'ready' || status.state === 'analyzing') {
    openLastBtn.hidden = false;
    openLastBtn.textContent = `Abrir «${status.project}»`;
    project.name = status.project;
  }
  setStatus('elige un proyecto para tejer');
  renderSaved();
  openUploader(true);
});

const communities = createCommunities({
  list: document.querySelector('#comms-list'),
  top: document.querySelector('#top-nodes'),
  topList: document.querySelector('#top-list'),
  cosmos,
  fmt,
  escapeHtml,
  rgb,
  kindName: KIND_NAME,
  onRegion(r) {
    openComms(false);
    if (brain.mode === 'weave') return travelTo(r);
    travelTo(r);
    setFollow(true);
  },
  onNode(n) {
    openComms(false);
    goToNode(n);
  },
});

const cine = { on: false, auto: false, timer: 0 };
function setCine(on) {
  cine.on = on;
  if (!on) cine.auto = false;
  document.body.classList.toggle('cine', on);
  cineBtn.setAttribute('aria-pressed', String(on));
  clearTimeout(cine.timer);
  cineHint.classList.toggle('show', on);
  if (on) {
    hideTip();
    cine.timer = setTimeout(() => cineHint.classList.remove('show'), 2200);
  }
}
cineBtn.addEventListener('click', () => setCine(!cine.on));

function openHelp(open) {
  helpEl.hidden = !open;
  helpBtn.setAttribute('aria-expanded', String(open));
  if (open) {
    closePopovers();
    hideTip();
    document.querySelector('#help-close').focus();
  }
}
helpBtn.addEventListener('click', () => openHelp(helpEl.hidden));
document.querySelector('#help-close').addEventListener('click', () => openHelp(false));
helpEl.addEventListener('click', (e) => {
  if (!e.target.closest('.card')) openHelp(false);
});

function escape() {
  if (!helpEl.hidden) return openHelp(false);
  if (cine.on) return setCine(false);
  closePopovers();
}

const recorder = createRecorder(canvas);
const rec = { timer: 0, last: null };
recCineBox.checked = load(CINE_KEY) === '1';
recCineBox.addEventListener('change', () => save(CINE_KEY, recCineBox.checked ? '1' : '0'));
const pad = (n) => String(n).padStart(2, '0');
function stamp(d = new Date()) {
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
}
function reelName() {
  const base = (project.name || (project.active ? 'proyecto' : 'cosmos')).toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'proyecto';
  return `cortex-${base}-${stamp()}.webm`;
}
function showRecording(on) {
  recordBtn.setAttribute('aria-pressed', String(on));
  recordBtn.title = on ? 'Detener y descargar el reel' : 'Grabar reel';
  recordBtn.setAttribute('aria-label', recordBtn.title);
  recChip.hidden = !on;
  document.body.classList.toggle('recording', on);
  clearInterval(rec.timer);
  if (on) {
    recTime.textContent = '00:00';
    rec.timer = setInterval(() => {
      const t = Math.floor(recorder.elapsed);
      recTime.textContent = `${pad(Math.floor(t / 60))}:${pad(t % 60)}`;
    }, 250);
  }
}
async function startRecording() {
  if (!recorder.supported) {
    toast('este navegador no puede grabar el lienzo: falta MediaRecorder con WebM', { kind: 'warn', ms: 5200 });
    return false;
  }
  try {
    recorder.start();
  } catch (err) {
    toast(`no se pudo empezar a grabar: ${err?.message || err}`, { kind: 'error' });
    return false;
  }
  showRecording(true);
  if (recCineBox.checked && !cine.on) {
    setCine(true);
    cine.auto = true;
  }
  return true;
}
async function stopRecording({ download = true } = {}) {
  if (!recorder.recording) return null;
  const auto = cine.auto;
  showRecording(false);
  let blob = null;
  try {
    blob = await recorder.stop();
  } catch (err) {
    toast(`la grabación falló: ${err?.message || err}`, { kind: 'error' });
  }
  if (auto && cine.on) setCine(false);
  if (!blob || !blob.size) {
    if (blob) toast('la grabación quedó vacía', { kind: 'warn' });
    return blob;
  }
  const name = reelName();
  rec.last = { size: blob.size, type: blob.type, name };
  if (download) {
    saveBlob(blob, name);
    toast(`reel guardado · ${name}`);
  }
  return blob;
}
recordBtn.addEventListener('click', () => (recorder.recording ? stopRecording() : startRecording()));

const NEST_NODES = cosmos.count;
const NEST_EDGES = cosmos.graph.edges;
let chipsT = 0;
let commsT = 0;
function updateChips(dt) {
  if (cosmos.graph.full && !project.fullWarned) {
    project.fullWarned = true;
    toast('el grafo superó la capacidad de la vista; el análisis completo sigue disponible en la exportación', { kind: 'warn', ms: 9000 });
  }
  if (!commsEl.hidden && (commsT -= dt) <= 0) {
    commsT = 1.5;
    if (brain.mode === 'weave') communities.render();
  }
  if (chipsEl.hidden || (chipsT -= dt) > 0) return;
  chipsT = 0.25;
  chip.files.textContent = fmt(project.woven || 0);
  chip.nodes.textContent = fmt(Math.max(0, cosmos.count - NEST_NODES));
  chip.edges.textContent = fmt(Math.max(0, cosmos.graph.edges - NEST_EDGES));
  chip.comms.textContent = fmt(Math.max(0, cosmos.regions.length - 1));
  const R = cosmos.regions[brain.region];
  chip.here.textContent = project.current ? `${R ? R.name + ' · ' : ''}${project.current.split('/').pop()}` : R ? `en ${R.name}` : 'en el nido';
}

let last = performance.now();
let time = 0;
let slow = 0;
let running = true;
let statusBeforeLoss = '';
const film = { on: false };
function frame(now) {
  requestAnimationFrame(frame);
  if (!running || film.on) {
    last = now;
    return;
  }
  const raw = (now - last) / 1000;
  const dt = Math.min(0.05, raw) * (reduced ? 0.6 : 1);
  last = now;
  slow = raw > 0.026 ? slow + raw : Math.max(0, slow - raw * 0.5);
  if (slow > 2.5 && pixelRatio > 1) {
    pixelRatio = Math.max(1, pixelRatio - 0.25);
    renderer.setPixelRatio(pixelRatio);
    resize();
    slow = 0;
  }
  tick(dt);
}
function tick(dt) {
  time += dt;
  if (statusTimer > 0) statusTimer -= dt;

  think(dt);
  if (weaver) weaver.update(dt);
  updateChips(dt);
  cosmos.setFocus(brain.mode === 'jump' ? brain.jumpTo : brain.region);
  spider.update(dt, time, brain.goal, brain.maxSpeed);
  cosmos.update(dt);
  nest.update(dt, time);
  if (cosmos.regions.length > 1 && rng() < dt * 0.6) nest.pulse(1 + Math.floor(rng() * (cosmos.regions.length - 1)));
  updateCamera(dt);
  sky.update(dt, time, camera, renderer.getPixelRatio());
  if (!cine.on) updateLabels();
  checkTip();
  renderer.render(scene, camera);
}
requestAnimationFrame(frame);
document.addEventListener('visibilitychange', () => {
  last = performance.now();
});
canvas.addEventListener('webglcontextlost', (e) => {
  e.preventDefault();
  running = false;
  statusBeforeLoss = statusEl.textContent;
  setStatus('la vista se pausó', 3);
  toast('se perdió el contexto gráfico · intentando recuperarlo…', { kind: 'warn', ms: 6000 });
});
canvas.addEventListener('webglcontextrestored', () => {
  running = true;
  last = performance.now();
  resize();
  statusTimer = 0;
  setStatus(statusBeforeLoss || 'vista recuperada');
  toast('vista recuperada');
});

window.__cortex = {
  film: {
    start() {
      film.on = true;
    },
    step(frames = 1, dt = 1 / 60) {
      for (let i = 0; i < frames; i++) tick(dt);
    },
    stop() {
      film.on = false;
      last = performance.now();
    },
  },
  cosmos,
  spider,
  brain,
  cam,
  sky,
  camera,
  renderer,
  project,
  travelTo,
  jumpTo,
  goToNode,
  spawn: cosmos.spawn,
  setSpeed,
  setCine,
  recorder,
  startRecording,
  stopRecording,
  get speed() {
    return weaveSpeed;
  },
  get weaver() {
    return weaver;
  },
  get lastRecording() {
    return rec.last;
  },
  get running() {
    return running;
  },
};
