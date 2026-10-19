import * as THREE from 'three';
import { mulberry32, gauss } from './rand.js';
import { pointsMaterial, pointsGeometry } from './materials.js';
import { createLightning } from './lightning.js';

const sunVert = `
  attribute vec3 color;
  attribute float aSize;
  attribute float aSeed;
  uniform float uTime;
  uniform float uPr;
  varying vec3 vColor;
  varying float vTw;
  varying float vRot;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = aSize * uPr;
    vTw = 0.82 + 0.18 * sin(uTime * (0.6 + aSeed) + aSeed * 20.0);
    vRot = aSeed * 0.6;
    vColor = color;
    gl_Position = projectionMatrix * mv;
  }
`;

const sunFrag = `
  varying vec3 vColor;
  varying float vTw;
  varying float vRot;
  void main() {
    vec2 p = (gl_PointCoord - 0.5) * 2.0;
    float c = cos(vRot), s = sin(vRot);
    vec2 q = vec2(c * p.x - s * p.y, s * p.x + c * p.y);
    float r = length(p);
    float core = exp(-r * r * 260.0);
    float glow = exp(-r * r * 40.0) * 0.35;
    float halo = exp(-r * r * 7.0) * 0.08;
    float spikes = exp(-abs(q.y) * 90.0) * exp(-abs(q.x) * 4.0) + exp(-abs(q.x) * 90.0) * exp(-abs(q.y) * 4.0);
    float a = (core + glow + halo + spikes * 0.22 * vTw) * smoothstep(1.0, 0.55, r);
    gl_FragColor = vec4(mix(vColor, vec3(1.0), core * 0.7), a * vTw);
  }
`;

const SUN_COLORS = [
  [1.0, 0.86, 0.62],
  [1.0, 0.72, 0.5],
  [0.72, 0.82, 1.0],
  [0.95, 0.95, 1.0],
  [1.0, 0.6, 0.55],
];

export function createSky(scene) {
  const rng = mulberry32(0x5ca1ab1e);
  const group = new THREE.Group();
  scene.add(group);
  const materials = [];
  const v = new THREE.Vector3();

  const addPoints = (geo, mat) => {
    const p = new THREE.Points(geo, mat);
    p.frustumCulled = false;
    group.add(p);
    materials.push(mat);
    return p;
  };
  const onSphere = (rMin, rMax) => v.set(gauss(rng), gauss(rng), gauss(rng)).normalize().multiplyScalar(rMin + rng() * (rMax - rMin));

  const starCount = 3200;
  const starGeo = pointsGeometry(starCount);
  {
    const sp = starGeo.attributes.position.array, sc = starGeo.attributes.color.array;
    const ss = starGeo.attributes.aSize.array, sa = starGeo.attributes.aAlpha.array;
    for (let i = 0; i < starCount; i++) {
      onSphere(260, 360);
      sp.set([v.x, v.y, v.z], i * 3);
      const w = rng();
      sc.set([0.75 + w * 0.25, 0.8 + w * 0.1, 1.0 - w * 0.15], i * 3);
      ss[i] = (0.14 + Math.pow(rng(), 5) * 0.4) * (v.length() / 100);
      sa[i] = 0.22 + rng() * 0.45;
    }
  }
  addPoints(starGeo, pointsMaterial({ fog: 0 }));

  const farClouds = 12, perCloud = 60;
  const farGeo = pointsGeometry(farClouds * perCloud);
  const clouds = [];
  {
    const p = farGeo.attributes.position.array, c = farGeo.attributes.color.array;
    const s = farGeo.attributes.aSize.array, a = farGeo.attributes.aAlpha.array;
    const palette = [[0.55, 0.45, 1.0], [1.0, 0.5, 0.6], [0.4, 0.75, 1.0], [1.0, 0.7, 0.45], [0.5, 0.95, 0.85]];
    for (let k = 0; k < farClouds; k++) {
      const center = onSphere(220, 290).clone();
      const col = palette[k % palette.length];
      const alt = palette[(k + 2) % palette.length];
      const stretch = new THREE.Vector3(gauss(rng), gauss(rng), gauss(rng)).normalize();
      clouds.push({ center, stretch, color: col, from: k * perCloud });
      for (let j = 0; j < perCloud; j++) {
        const i = k * perCloud + j;
        const along = gauss(rng) * 28;
        p.set([
          center.x + stretch.x * along + gauss(rng) * 12,
          center.y + stretch.y * along + gauss(rng) * 12,
          center.z + stretch.z * along + gauss(rng) * 12,
        ], i * 3);
        const m = rng() * 0.45;
        c.set(col.map((x, q) => x * (1 - m) + alt[q] * m), i * 3);
        s[i] = 26 + rng() * 40;
        a[i] = 0.012 + rng() * 0.022;
      }
    }
  }
  const farMat = pointsMaterial({ fog: 0, maxPx: 640, heatSize: 0.15 });
  farMat.uniforms.uHot.value.setRGB(0.88, 0.92, 1.0);
  addPoints(farGeo, farMat);

  const skyBolts = createLightning(group, { fog: false, flashSize: 14, maxFlashPx: 400 });
  materials.push(...skyBolts.materials);
  const TEMPESTS = 5;
  const glowGeo = pointsGeometry(TEMPESTS, { size: 1, alpha: 0 });
  const glowMat = pointsMaterial({ fog: 0, heatSize: 0, maxPx: 760 });
  addPoints(glowGeo, glowMat);
  const farHeat = farGeo.attributes.aHeat.array;
  const farPos = farGeo.attributes.position.array;
  const tempests = Array.from({ length: TEMPESTS }, () => ({ active: false }));
  let tempestT = 2.5;
  const camDir = new THREE.Vector3();
  const sc = new THREE.Vector3();
  const b0 = new THREE.Vector3();
  const b1 = new THREE.Vector3();

  function startTempest(camera) {
    const T = tempests.find((x) => !x.active);
    if (!T) return;
    camera.getWorldDirection(camDir);
    const busy = new Set(tempests.filter((x) => x.active).map((x) => x.cloud));
    const free = clouds.filter((c) => !busy.has(c));
    const visible = free.filter((c) => c.center.clone().normalize().dot(camDir) > 0.35);
    const pool = visible.length && rng() < 0.5 ? visible : free;
    if (!pool.length) return;
    const cl = pool[Math.floor(rng() * pool.length)];
    T.cloud = cl;
    const along = gauss(rng) * 18;
    T.center = cl.center.clone().addScaledVector(cl.stretch, along).add(new THREE.Vector3(gauss(rng), gauss(rng), gauss(rng)).multiplyScalar(6));
    T.size = 20 + rng() * 14;
    T.color = cl.color.map((c) => c * 0.3 + 0.7);
    T.lit = [];
    for (let i = cl.from; i < cl.from + perCloud; i++) {
      sc.set(farPos[i * 3], farPos[i * 3 + 1], farPos[i * 3 + 2]);
      const d = sc.distanceTo(T.center);
      if (d < T.size * 1.8) T.lit.push([i, 1 - d / (T.size * 1.8)]);
    }
    T.flashes = [];
    let at = 0;
    const n = 3 + Math.floor(rng() * 4);
    for (let k = 0; k < n; k++) {
      T.flashes.push({ at, dur: 0.08 + rng() * 0.2, power: 0.6 + rng() * 0.4, bolt: rng() < 0.55, done: false });
      at += 0.1 + rng() * 0.4;
    }
    T.end = at + 0.4;
    T.t = 0;
    T.active = true;
    const k = tempests.indexOf(T);
    glowGeo.attributes.position.array.set([T.center.x, T.center.y, T.center.z], k * 3);
    glowGeo.attributes.color.array.set(T.color, k * 3);
    glowGeo.attributes.aSize.array[k] = T.size * 2.6;
    glowGeo.attributes.position.needsUpdate = glowGeo.attributes.color.needsUpdate = glowGeo.attributes.aSize.needsUpdate = true;
  }

  function updateTempests(dt) {
    const ga = glowGeo.attributes.aAlpha.array;
    let touched = false;
    tempests.forEach((T, k) => {
      if (!T.active) return;
      touched = true;
      T.t += dt;
      let I = 0;
      for (const f of T.flashes) {
        const u = (T.t - f.at) / f.dur;
        if (u >= 0 && u <= 1) I = Math.max(I, f.power * Math.pow(1 - u, 0.5) * (0.8 + rng() * 0.2));
        if (f.bolt && !f.done && u >= 0) {
          f.done = true;
          b0.copy(T.center).add(sc.set(gauss(rng), gauss(rng), gauss(rng)).multiplyScalar(T.size * 0.3));
          b1.copy(b0).add(sc.set(gauss(rng), gauss(rng), gauss(rng)).normalize().multiplyScalar(T.size * (0.6 + rng() * 0.7)));
          skyBolts.strike(b0, b1, T.color, 1.3);
        }
      }
      ga[k] = 0.28 * I;
      for (const [i, w] of T.lit) farHeat[i] = w * I * 5;
      if (T.t >= T.end) {
        T.active = false;
        ga[k] = 0;
        for (const [i] of T.lit) farHeat[i] = 0;
      }
    });
    if (touched) {
      glowGeo.attributes.aAlpha.needsUpdate = true;
      farGeo.attributes.aHeat.needsUpdate = true;
    }
  }

  const galaxies = [];
  for (let g = 0; g < 3; g++) {
    const center = onSphere(300, 340).clone();
    const tilt = new THREE.Quaternion(gauss(rng), gauss(rng), gauss(rng), gauss(rng)).normalize();
    const R = 12 + rng() * 10;
    const scale = center.length() / 100;
    const parts = [];
    for (const core of [false, true]) {
      const count = core ? 700 : 1700;
      const geo = pointsGeometry(count);
      const p = geo.attributes.position.array, c = geo.attributes.color.array;
      const s = geo.attributes.aSize.array, a = geo.attributes.aAlpha.array;
      for (let i = 0; i < count; i++) {
        if (core) v.set(gauss(rng) * R * 0.14, gauss(rng) * R * 0.05, gauss(rng) * R * 0.14);
        else {
          const t = Math.pow(rng(), 0.7);
          const ang = Math.floor(rng() * 2) * Math.PI + t * 4.2;
          const rad = R * (0.12 + t);
          v.set(Math.cos(ang) * rad + gauss(rng) * R * 0.06, gauss(rng) * R * 0.025, Math.sin(ang) * rad + gauss(rng) * R * 0.06);
        }
        p.set([v.x, v.y, v.z], i * 3);
        c.set(core ? [1.0, 0.86, 0.7] : rng() < 0.15 ? [1.0, 0.65, 0.75] : [0.7, 0.8, 1.0], i * 3);
        s[i] = (core ? 0.28 : 0.2) * scale;
        a[i] = core ? 0.35 + rng() * 0.3 : 0.15 + rng() * 0.3;
      }
      const pts = addPoints(geo, pointsMaterial({ fog: 0 }));
      pts.position.copy(center);
      pts.quaternion.copy(tilt);
      parts.push({ pts, speed: (core ? 0.22 : 0.07) * (rng() < 0.5 ? 1 : -1) });
    }
    parts[1].speed = Math.sign(parts[0].speed) * Math.abs(parts[1].speed);
    galaxies.push(parts);
  }
  const spinAxis = new THREE.Vector3(0, 1, 0);
  const spinQ = new THREE.Quaternion();

  const suns = 18;
  const sunGeo = new THREE.BufferGeometry();
  {
    const p = new Float32Array(suns * 3), c = new Float32Array(suns * 3);
    const s = new Float32Array(suns), seed = new Float32Array(suns);
    for (let i = 0; i < suns; i++) {
      onSphere(240, 320);
      p.set([v.x, v.y, v.z], i * 3);
      const main = i === 0;
      c.set(main ? SUN_COLORS[0] : SUN_COLORS[Math.floor(rng() * SUN_COLORS.length)], i * 3);
      s[i] = main ? 200 : 46 + Math.pow(rng(), 2) * 90;
      seed[i] = rng() * 3;
    }
    sunGeo.setAttribute('position', new THREE.BufferAttribute(p, 3));
    sunGeo.setAttribute('color', new THREE.BufferAttribute(c, 3));
    sunGeo.setAttribute('aSize', new THREE.BufferAttribute(s, 1));
    sunGeo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
  }
  const sunMat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uPr: { value: 1 } },
    vertexShader: sunVert,
    fragmentShader: sunFrag,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const sunPts = new THREE.Points(sunGeo, sunMat);
  sunPts.frustumCulled = false;
  group.add(sunPts);

  const METEORS = 4, MSEG = 10;
  const mPos = new Float32Array(METEORS * MSEG * 6);
  const mCol = new Float32Array(METEORS * MSEG * 6);
  const mGeo = new THREE.BufferGeometry();
  mGeo.setAttribute('position', new THREE.BufferAttribute(mPos, 3));
  mGeo.setAttribute('color', new THREE.BufferAttribute(mCol, 3));
  const mLines = new THREE.LineSegments(
    mGeo,
    new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false })
  );
  mLines.frustumCulled = false;
  group.add(mLines);
  const meteors = Array.from({ length: METEORS }, () => ({ life: 0, dur: 1, p: new THREE.Vector3(), d: new THREE.Vector3(), len: 0, speed: 0 }));
  let nextMeteor = 3;
  const head = new THREE.Vector3();

  return {
    materials,
    update(dt, time, camera, pixelRatio) {
      group.position.copy(camera.position);
      sunMat.uniforms.uTime.value = time;

      for (const parts of galaxies) {
        for (const part of parts) part.pts.quaternion.multiply(spinQ.setFromAxisAngle(spinAxis, part.speed * dt));
      }

      tempestT -= dt;
      if (tempestT <= 0) {
        tempestT = 0.7 + rng() * 1.5;
        startTempest(camera);
      }
      updateTempests(dt);
      skyBolts.update(dt);
      sunMat.uniforms.uPr.value = pixelRatio;

      nextMeteor -= dt;
      if (nextMeteor <= 0) {
        nextMeteor = 3 + rng() * 6;
        const m = meteors.find((x) => x.life <= 0);
        if (m) {
          camera.getWorldDirection(v);
          m.p.copy(v).multiplyScalar(190).add(new THREE.Vector3(gauss(rng), gauss(rng), gauss(rng)).multiplyScalar(70));
          m.d.set(gauss(rng), gauss(rng), gauss(rng)).cross(v).normalize();
          m.len = 14 + rng() * 16;
          m.speed = 80 + rng() * 60;
          m.dur = 0.9 + rng() * 0.8;
          m.life = m.dur;
        }
      }
      meteors.forEach((m, k) => {
        const o0 = k * MSEG * 6;
        if (m.life <= 0) {
          mCol.fill(0, o0, o0 + MSEG * 6);
          return;
        }
        m.life -= dt;
        m.p.addScaledVector(m.d, m.speed * dt);
        const fade = Math.sin(Math.PI * Math.max(0, m.life) / m.dur);
        for (let s = 0; s < MSEG; s++) {
          const o = o0 + s * 6;
          const t0 = s / MSEG, t1 = (s + 1) / MSEG;
          head.copy(m.p).addScaledVector(m.d, -m.len * t0);
          mPos.set([head.x, head.y, head.z], o);
          head.copy(m.p).addScaledVector(m.d, -m.len * t1);
          mPos.set([head.x, head.y, head.z], o + 3);
          const i0 = 0.55 * fade * (1 - t0) ** 2, i1 = 0.55 * fade * (1 - t1) ** 2;
          mCol.set([0.85 * i0, 0.9 * i0, i0, 0.85 * i1, 0.9 * i1, i1], o);
        }
      });
      mGeo.attributes.position.needsUpdate = true;
      mGeo.attributes.color.needsUpdate = true;
    },
  };
}
