import * as THREE from 'three';

const pointVert = `
  attribute vec3 color;
  attribute float aSize;
  attribute float aAlpha;
  attribute float aHeat;
  uniform float uPx;
  uniform float uFog;
  uniform float uHeatSize;
  uniform float uMaxPx;
  uniform float uBoost;
  varying vec3 vColor;
  varying float vAlpha;
  varying float vHeat;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float d = max(0.05, -mv.z);
    float size = aSize * (1.0 + aHeat * uHeatSize) * uPx / d;
    float sub = clamp(size * 1.4, 0.45, 1.0);
    gl_PointSize = clamp(size, 1.0, uMaxPx);
    vColor = color;
    vHeat = aHeat;
    vAlpha = aAlpha * sub * uBoost * exp(-uFog * d * d);
    gl_Position = projectionMatrix * mv;
  }
`;

const pointFrag = `
  uniform vec3 uHot;
  varying vec3 vColor;
  varying float vAlpha;
  varying float vHeat;
  void main() {
    vec2 p = gl_PointCoord - 0.5;
    float r = length(p) * 2.0;
    if (r > 1.0) discard;
    float a = pow(1.0 - r, 2.4);
    vec3 col = mix(vColor, uHot, clamp(vHeat * 0.7, 0.0, 0.85));
    float e = vAlpha * (1.0 + vHeat * 0.9);
    gl_FragColor = vec4(col, min(e * a, 1.0));
  }
`;

export function pointsMaterial({ fog = 0.0016, heatSize = 0.6, maxPx = 48 } = {}) {
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uPx: { value: 600 },
      uFog: { value: fog },
      uHeatSize: { value: heatSize },
      uMaxPx: { value: maxPx },
      uBoost: { value: 1 },
      uHot: { value: new THREE.Color(1.0, 0.93, 0.82) },
    },
    vertexShader: pointVert,
    fragmentShader: pointFrag,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  mat.userData.fog0 = fog;
  return mat;
}

export function linesMaterial() {
  return new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    fog: true,
  });
}

export function pointsGeometry(count, { size = 0.05, alpha = 1, color = [1, 1, 1] } = {}) {
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const col = new Float32Array(count * 3);
  const sz = new Float32Array(count).fill(size);
  const al = new Float32Array(count).fill(alpha);
  const ht = new Float32Array(count);
  for (let i = 0; i < count; i++) col.set(color, i * 3);
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  g.setAttribute('aSize', new THREE.BufferAttribute(sz, 1));
  g.setAttribute('aAlpha', new THREE.BufferAttribute(al, 1));
  g.setAttribute('aHeat', new THREE.BufferAttribute(ht, 1));
  return g;
}
