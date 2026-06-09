// Vibe 3D engine — experimental WebGL renderer for `renderer:"3d"` scenes.
//
// Parallel to the 2D canvas engine in display.html. A 3D scene is the same JSON
// envelope (id, name, MU/TH/UR metadata) but carries `camera`, `environment`,
// and an `objects[]` array. Each object has a `type` dispatched to a builder
// below, optional `params`, and an optional `motion` block of expression
// strings evaluated per frame (same model as the 2D engine).
//
// Designed for projection onto a gaming table: dark, slow, radially-composed,
// cinematic. The look comes from a real post pipeline — ACES tone mapping +
// UnrealBloom + a film-grain/vignette pass — not from the raw geometry. Fully
// procedural (no external models/images), offline- and OBS/CEF-safe (WebGL2,
// no WebGPU).

import * as THREE from 'three';
import { EffectComposer } from '/static/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from '/static/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from '/static/jsm/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from '/static/jsm/postprocessing/ShaderPass.js';
import { OutputPass } from '/static/jsm/postprocessing/OutputPass.js';

const TAU = Math.PI * 2;

// ── Motion evaluator (math-only expressions of `t` in ms) ──────────────────
const _motionCache = new Map();
function compile(expr) {
  if (_motionCache.has(expr)) return _motionCache.get(expr);
  const safe = expr
    .replace(/\bsin\b/g, 'Math.sin').replace(/\bcos\b/g, 'Math.cos')
    .replace(/\btan\b/g, 'Math.tan').replace(/\babs\b/g, 'Math.abs')
    .replace(/\bfloor\b/g, 'Math.floor').replace(/\bceil\b/g, 'Math.ceil')
    .replace(/\bsqrt\b/g, 'Math.sqrt').replace(/\bpow\b/g, 'Math.pow')
    .replace(/\bmax\b/g, 'Math.max').replace(/\bmin\b/g, 'Math.min')
    .replace(/\bTAU\b/g, '(Math.PI*2)').replace(/\bPI\b/g, 'Math.PI');
  let fn;
  try { fn = new Function('t', `"use strict";try{return(${safe});}catch(e){return 0;}`); }
  catch (_) { fn = () => 0; }
  _motionCache.set(expr, fn);
  return fn;
}
function evalMotion(motion, t) {
  const out = {};
  if (!motion) return out;
  for (const [k, expr] of Object.entries(motion)) {
    if (typeof expr === 'string') {
      const v = compile(expr)(t);
      if (v !== null && !isNaN(v)) out[k] = v;
    }
  }
  return out;
}

// ── Procedural glow texture (white, smooth gaussian falloff) ───────────────
// Tinted per-use via material.color / vertex colors. Soft edges read well
// under additive blending + bloom.
let _glowTex = null;
function glowTexture() {
  if (_glowTex) return _glowTex;
  const s = 128, cv = document.createElement('canvas');
  cv.width = cv.height = s;
  const g = cv.getContext('2d');
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0.0, 'rgba(255,255,255,1.0)');
  grad.addColorStop(0.15, 'rgba(255,255,255,0.85)');
  grad.addColorStop(0.40, 'rgba(255,255,255,0.30)');
  grad.addColorStop(0.75, 'rgba(255,255,255,0.06)');
  grad.addColorStop(1.0, 'rgba(255,255,255,0.0)');
  g.fillStyle = grad; g.fillRect(0, 0, s, s);
  _glowTex = new THREE.CanvasTexture(cv);
  _glowTex.colorSpace = THREE.SRGBColorSpace;
  return _glowTex;
}

// Crisp star sprite — small bright core, tight falloff, so points read as
// stars rather than soft blobs.
let _starTex = null;
function starTexture() {
  if (_starTex) return _starTex;
  const s = 64, cv = document.createElement('canvas');
  cv.width = cv.height = s;
  const g = cv.getContext('2d');
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0.0, 'rgba(255,255,255,1.0)');
  grad.addColorStop(0.10, 'rgba(255,255,255,0.95)');
  grad.addColorStop(0.22, 'rgba(255,255,255,0.35)');
  grad.addColorStop(0.45, 'rgba(255,255,255,0.06)');
  grad.addColorStop(1.0, 'rgba(255,255,255,0.0)');
  g.fillStyle = grad; g.fillRect(0, 0, s, s);
  _starTex = new THREE.CanvasTexture(cv);
  _starTex.colorSpace = THREE.SRGBColorSpace;
  return _starTex;
}

function rand(a, b) { return a + Math.random() * (b - a); }

// GLSL for the accretion disk: each particle orbits at a Keplerian rate
// (inner faster than outer) and drifts slowly inward, so it reads as matter
// spiralling into the hole rather than a rigid disc spinning.
const DISK_VERT = `
  uniform float uTime, uInner, uOuter, uSpin, uInfall, uSize, uBrightness;
  uniform vec3 cHot, cMid, cOut;
  attribute float aAngle; attribute float aSeed; attribute float aY;
  varying vec3 vCol; varying float vA;
  void main() {
    float m = fract(aSeed - uTime * uInfall);          // 1=outer -> 0=falling in
    float radius = mix(uInner, uOuter, pow(m, 1.7));
    float omega = uSpin / pow(radius, 1.5);            // Keplerian: inner faster
    float ang = aAngle + uTime * omega;
    vec3 pos = vec3(cos(ang) * radius,
                    aY * (0.04 + 0.02 * (radius / uOuter)) * radius,
                    sin(ang) * radius);
    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = uSize * (300.0 / max(0.001, -mv.z));
    vec3 c = m < 0.5 ? mix(cHot, cMid, m * 2.0) : mix(cMid, cOut, (m - 0.5) * 2.0);
    vCol = c * (uBrightness * (1.7 - m * 1.2));         // inner hotter/brighter
    vA = smoothstep(0.0, 0.06, m) * (1.0 - smoothstep(0.93, 1.0, m)); // hide wrap
  }`;
const DISK_FRAG = `
  uniform sampler2D uTex; varying vec3 vCol; varying float vA;
  void main() { vec4 t = texture2D(uTex, gl_PointCoord); gl_FragColor = vec4(vCol, t.a * vA); }`;

// ── Film-grain + vignette pass (linear space, before OutputPass) ───────────
const GrainVignetteShader = {
  uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uGrain: { value: 0.045 }, uVignette: { value: 0.55 } },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float uTime; uniform float uGrain; uniform float uVignette;
    varying vec2 vUv;
    float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
    void main(){
      vec4 c = texture2D(tDiffuse, vUv);
      vec2 d = vUv - 0.5;
      float vig = 1.0 - smoothstep(0.42, 0.86, length(d)) * uVignette;
      c.rgb *= vig;
      float g = (hash(vUv + fract(uTime)) - 0.5) * uGrain;
      c.rgb += g;
      gl_FragColor = c;
    }`,
};

// ── Object builders ────────────────────────────────────────────────────────
// Each returns { object3d, update(t) }; update is optional intrinsic animation.
const BUILDERS = {

  // Stars on a sphere shell, slight colour variation, gentle drift.
  starfield(p) {
    const count = Math.min(p.count ?? 1600, 8000);
    const radius = p.radius ?? 140;
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);
    const warm = new THREE.Color(p.warm || '#ffd9a8');
    const cool = new THREE.Color(p.cool || '#9fc0ff');
    const base = new THREE.Color(p.color || '#ffffff');
    for (let i = 0; i < count; i++) {
      const u = Math.random(), v = Math.random();
      const theta = TAU * u, phi = Math.acos(2 * v - 1);
      const r = radius * (0.55 + 0.45 * Math.random());
      pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
      const tint = base.clone().lerp(Math.random() < 0.5 ? warm : cool, Math.random() * 0.5);
      const b = 0.5 + Math.pow(Math.random(), 3) * 1.6; // a few bright ones bloom
      col[i * 3] = tint.r * b; col[i * 3 + 1] = tint.g * b; col[i * 3 + 2] = tint.b * b;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    const obj = new THREE.Points(geo, new THREE.PointsMaterial({
      size: p.size ?? 1.1, map: starTexture(), vertexColors: true,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true,
    }));
    const spin = p.spin ?? 0.0000035;
    return { object3d: obj, update: (t) => { obj.rotation.y = t * spin; } };
  },

  // Soft additive cloud puffs — gas / nebula volume. Large, faint, blended.
  nebula_volume(p) {
    const count = Math.min(p.count ?? 22, 90);
    const spread = p.spread ?? 36;
    const flat = p.flat ?? 0.45; // squash vertically so it reads as a disc from above
    const group = new THREE.Group();
    const tex = glowTexture();
    const colors = (p.colors || [p.color || '#5a1024', '#1a0a30']).map((c) => new THREE.Color(c));
    const sprites = [];
    for (let i = 0; i < count; i++) {
      const tint = colors[i % colors.length].clone().lerp(colors[(i + 1) % colors.length], Math.random());
      const mat = new THREE.SpriteMaterial({
        map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
        opacity: rand(p.alpha_min ?? 0.05, p.alpha_max ?? 0.16), color: tint,
      });
      const s = new THREE.Sprite(mat);
      s.position.set(rand(-spread, spread), rand(-spread, spread) * flat, rand(-spread, spread));
      const sc = rand(p.size_min ?? 16, p.size_max ?? 46);
      s.scale.set(sc, sc, 1);
      s.userData.phase = Math.random() * TAU;
      s.userData.baseA = mat.opacity;
      group.add(s); sprites.push(s);
    }
    const drift = p.drift ?? 0.000012;
    return {
      object3d: group,
      update: (t) => {
        group.rotation.y = t * drift;
        for (const s of sprites)
          s.material.opacity = s.userData.baseA * (0.55 + 0.45 * Math.sin(t * 0.00025 + s.userData.phase));
      },
    };
  },

  // The hero set-piece: black core, bright photon ring, hot accretion disk,
  // soft halo. Built to bloom.
  dark_core(p) {
    const group = new THREE.Group();
    const R = p.radius ?? 2.2;
    const tilt = p.tilt ?? 1.15;

    const core = new THREE.Mesh(new THREE.SphereGeometry(R, 48, 48),
      new THREE.MeshBasicMaterial({ color: 0x000000 }));
    group.add(core);

    // Soft halo shell (backside additive) — outer glow.
    const halo = new THREE.Mesh(new THREE.SphereGeometry(R * 1.6, 40, 40),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(p.glow || '#5a0c1e'), transparent: true, opacity: 0.45,
        side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false,
      }));
    group.add(halo);

    // Bright photon ring (thin, high value -> blooms into a bright halo edge).
    const ring = new THREE.Mesh(new THREE.TorusGeometry(R * 1.18, R * 0.018, 12, 160),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(p.photon || '#ffe6b0') }));
    ring.material.color.multiplyScalar(2.2);
    ring.rotation.x = Math.PI / 2;
    const ringHolder = new THREE.Group(); ringHolder.add(ring); ringHolder.rotation.x = tilt;
    group.add(ringHolder);

    // Accretion disk — GPU shader particles with Keplerian differential spin
    // and slow inward drift, so it reads as matter falling in.
    const dcount = Math.min(p.disk_count ?? 4000, 14000);
    const inner = R * 1.25, outer = R * (p.disk_radius ?? 4.8);
    const posD = new Float32Array(dcount * 3); // unused 'position' (ShaderMaterial needs it)
    const aAngle = new Float32Array(dcount), aSeed = new Float32Array(dcount), aY = new Float32Array(dcount);
    for (let i = 0; i < dcount; i++) {
      aAngle[i] = Math.random() * TAU;
      aSeed[i] = Math.random();
      aY[i] = rand(-1, 1);
    }
    const dgeo = new THREE.BufferGeometry();
    dgeo.setAttribute('position', new THREE.BufferAttribute(posD, 3));
    dgeo.setAttribute('aAngle', new THREE.BufferAttribute(aAngle, 1));
    dgeo.setAttribute('aSeed', new THREE.BufferAttribute(aSeed, 1));
    dgeo.setAttribute('aY', new THREE.BufferAttribute(aY, 1));
    const diskMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 }, uInner: { value: inner }, uOuter: { value: outer },
        uSpin: { value: p.disk_spin ?? 0.00028 }, uInfall: { value: p.disk_infall ?? 0.0000115 },
        uSize: { value: p.disk_dot ?? 0.16 }, uBrightness: { value: p.disk_brightness ?? 1.0 },
        uTex: { value: glowTexture() },
        cHot: { value: new THREE.Color(p.disk_hot || '#fff0c8') },
        cMid: { value: new THREE.Color(p.disk_mid || '#ff7a2a') },
        cOut: { value: new THREE.Color(p.disk_out || '#8a0e16') },
      },
      vertexShader: DISK_VERT, fragmentShader: DISK_FRAG,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const disk = new THREE.Points(dgeo, diskMat);
    disk.rotation.x = tilt;
    disk.frustumCulled = false; // positions live in the shader; bounding sphere is wrong
    group.add(disk);

    const ringSpin = p.disk_spin ?? 0.00028;
    return {
      object3d: group,
      update: (t) => {
        diskMat.uniforms.uTime.value = t;
        ring.rotation.z = -t * ringSpin * 0.4;
        halo.material.opacity = 0.4 + 0.1 * Math.sin(t * 0.0008);
      },
    };
  },

  accretion_disk(p) { return BUILDERS.dark_core({ ...p, radius: 0.001, glow: 'rgba(0,0,0,0)', photon: 'rgba(0,0,0,0)' }); },

  // Bright drifting embers / sparks — beautiful under bloom.
  embers(p) {
    const count = Math.min(p.count ?? 300, 2000);
    const spread = p.spread ?? 24;
    const flat = p.flat ?? 1.0;
    const pos = new Float32Array(count * 3), col = new Float32Array(count * 3);
    const c1 = new THREE.Color(p.color || '#ff6a1e'), c2 = new THREE.Color(p.color2 || '#ffd089');
    for (let i = 0; i < count; i++) {
      pos[i * 3]     = rand(-spread, spread);
      pos[i * 3 + 1] = rand(-spread, spread) * flat;
      pos[i * 3 + 2] = rand(-spread, spread);
      const c = c1.clone().lerp(c2, Math.random()), b = 1.2 + Math.random();
      col[i * 3] = c.r * b; col[i * 3 + 1] = c.g * b; col[i * 3 + 2] = c.b * b;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    const obj = new THREE.Points(geo, new THREE.PointsMaterial({
      size: p.size ?? 0.5, map: glowTexture(), vertexColors: true,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    const spin = p.spin ?? 0.00006;
    return { object3d: obj, update: (t) => { obj.rotation.y = t * spin; obj.position.y = Math.sin(t * 0.0002) * (p.bob ?? 1.5); } };
  },

  // A brooding lit world — dark body + glowing atmospheric limb. Needs a
  // scene `light` to carve the crescent. Very Alien.
  planet(p) {
    const group = new THREE.Group();
    const R = p.radius ?? 6;
    const body = new THREE.Mesh(new THREE.SphereGeometry(R, 64, 64),
      new THREE.MeshStandardMaterial({
        color: new THREE.Color(p.color || '#241b16'), roughness: 0.95, metalness: 0.05,
        emissive: new THREE.Color(p.night || '#0a0406'), emissiveIntensity: 0.5,
      }));
    group.add(body);
    const atmo = new THREE.Mesh(new THREE.SphereGeometry(R * 1.05, 64, 64),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(p.atmosphere || '#ff5a2a'), transparent: true, opacity: 0.4,
        side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false,
      }));
    group.add(atmo);
    const spin = p.spin ?? 0.000015;
    return { object3d: group, update: (t) => { body.rotation.y = t * spin; } };
  },

  // Distant dark wreck: near-black hull, bloom-bright window lights + beacon.
  derelict_hull(p) {
    const group = new THREE.Group();
    const skin = new THREE.MeshStandardMaterial({
      color: new THREE.Color(p.color || '#141210'), roughness: 0.9, metalness: 0.55,
      emissive: new THREE.Color('#040303'), emissiveIntensity: 0.6,
    });
    const hull = new THREE.Mesh(new THREE.CapsuleGeometry(0.55, 6, 6, 14), skin);
    hull.rotation.z = Math.PI / 2;
    group.add(hull);
    const spine = new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.3, 0.3), skin);
    group.add(spine);
    for (const sx of [-1.5, 1.5]) {
      const fin = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.12, 2.6), skin);
      fin.position.set(sx, 0, 0); group.add(fin);
    }
    const lit = new THREE.Color(p.lights || '#ffb060');
    for (let i = 0; i < 10; i++) {
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.05, 6, 6),
        new THREE.MeshBasicMaterial({ color: lit.clone().multiplyScalar(rand(1.2, 2.2)) }));
      dot.position.set(rand(-3, 3), rand(-0.35, 0.35), 0.5); group.add(dot);
    }
    const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.08, 8, 8),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(p.beacon || '#ff2a18') }));
    beacon.position.set(-3.2, 0.4, 0); group.add(beacon);
    group.scale.setScalar(p.scale ?? 1);
    const tx = p.tumble ?? 0.000018, ty = p.tumble_y ?? 0.00003;
    return {
      object3d: group,
      update: (t) => {
        group.rotation.x = t * tx; group.rotation.y = t * ty;
        const b = 0.4 + 0.6 * Math.pow(Math.max(0, Math.sin(t * 0.002)), 6); // blink
        beacon.material.color.setRGB(b * 1.8, b * 0.3, b * 0.2);
      },
    };
  },

  debris_field(p) {
    const count = Math.min(p.count ?? 50, 220);
    const spread = p.spread ?? 22;
    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(p.color || '#23201c'), roughness: 0.95, metalness: 0.4,
      emissive: new THREE.Color(p.emissive || '#060403'), emissiveIntensity: 0.4,
    });
    const geos = [new THREE.TetrahedronGeometry(1), new THREE.BoxGeometry(1.4, 0.6, 0.9), new THREE.IcosahedronGeometry(0.8, 0)];
    const chunks = [];
    for (let i = 0; i < count; i++) {
      const m = new THREE.Mesh(geos[i % geos.length], mat);
      m.position.set(rand(-spread, spread), rand(-spread * 0.5, spread * 0.5), rand(-spread, spread));
      m.scale.setScalar(rand(p.size_min ?? 0.15, p.size_max ?? 0.9));
      m.rotation.set(Math.random() * TAU, Math.random() * TAU, Math.random() * TAU);
      m.userData.rs = [rand(-0.0003, 0.0003), rand(-0.0003, 0.0003), rand(-0.0003, 0.0003)];
      group.add(m); chunks.push(m);
    }
    const drift = p.drift ?? 0.000008;
    return {
      object3d: group,
      update: (t) => { group.rotation.y = t * drift; for (const m of chunks) { m.rotation.x += m.userData.rs[0]; m.rotation.y += m.userData.rs[1]; } },
    };
  },

  dust_motes(p) {
    const count = Math.min(p.count ?? 400, 2500);
    const spread = p.spread ?? 40;
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = rand(-spread, spread); pos[i * 3 + 1] = rand(-spread, spread); pos[i * 3 + 2] = rand(-spread, spread);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const obj = new THREE.Points(geo, new THREE.PointsMaterial({
      size: p.size ?? 0.14, map: glowTexture(), transparent: true, opacity: p.opacity ?? 0.4,
      depthWrite: false, blending: THREE.AdditiveBlending, color: new THREE.Color(p.color || '#7a6f64'),
    }));
    const drift = p.drift ?? 0.000015;
    return { object3d: obj, update: (t) => { obj.rotation.x = t * drift; obj.rotation.z = t * drift * 0.6; } };
  },

  light(p) {
    const kind = p.kind || 'point';
    let l;
    if (kind === 'ambient') {
      l = new THREE.AmbientLight(new THREE.Color(p.color || '#ffffff'), p.intensity ?? 0.5);
    } else if (kind === 'directional') {
      // Parallel rays — ideal for a distant sun carving a planet crescent.
      l = new THREE.DirectionalLight(new THREE.Color(p.color || '#ffd9b0'), p.intensity ?? 2.4);
      const pp = p.position || [40, 10, 20]; l.position.set(pp[0], pp[1], pp[2]);
    } else {
      l = new THREE.PointLight(new THREE.Color(p.color || '#ff6633'), p.intensity ?? 60, p.distance ?? 0, p.decay ?? 2);
      const pp = p.position || [0, 0, 0]; l.position.set(pp[0], pp[1], pp[2]);
    }
    return { object3d: l };
  },

  grid(p) {
    const g = new THREE.GridHelper(p.size ?? 80, p.divisions ?? 40,
      new THREE.Color(p.color || '#1e6e3c'), new THREE.Color(p.color || '#0e3a20'));
    g.material.transparent = true; g.material.opacity = p.opacity ?? 0.2;
    g.position.y = p.y ?? -6;
    return { object3d: g };
  },
};

// ── Engine ────────────────────────────────────────────────────────────────
export class Vibe3DEngine {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;
    this.scene = null; this.camera = null; this.composer = null;
    this.bloom = null; this.grainPass = null;
    this.updaters = []; this.motionTargets = [];
    this.camMotion = null; this.camBasePos = [0, 0, 12]; this.camLookAt = [0, 0, 0];
    this._w = 1920; this._h = 1080;
  }

  resize(w, h) {
    this._w = w; this._h = h;
    this.renderer.setSize(w, h, false);
    if (this.camera) { this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); }
    if (this.composer) this.composer.setSize(w, h);
  }

  load(def) {
    this._disposeScene();
    const scene = new THREE.Scene();
    const env = def.environment || {};
    scene.background = new THREE.Color(env.background || '#000000');
    if (env.fog) scene.fog = new THREE.Fog(new THREE.Color(env.fog.color || '#000000'), env.fog.near ?? 10, env.fog.far ?? 80);

    const cam = def.camera || {};
    const camera = new THREE.PerspectiveCamera(cam.fov ?? 55, this._w / this._h, 0.1, 3000);
    this.camBasePos = cam.position || [0, 0, 14];
    this.camLookAt = cam.lookAt || [0, 0, 0];
    camera.position.set(...this.camBasePos);
    camera.lookAt(...this.camLookAt);
    this.camMotion = cam.motion || null;

    scene.add(new THREE.AmbientLight(0xffffff, env.ambient ?? 0.22));

    this.updaters = []; this.motionTargets = [];
    for (const o of (def.objects || [])) {
      const build = BUILDERS[o.type];
      if (!build) continue;
      let built; try { built = build(o.params || {}); } catch (_) { continue; }
      const obj = built.object3d;
      const pp = (o.params && o.params.position) || null;
      const rr = (o.params && o.params.rotation) || null;
      if (pp) obj.position.set(pp[0], pp[1], pp[2]);
      if (rr) obj.rotation.set(rr[0], rr[1], rr[2]);
      scene.add(obj);
      if (built.update) this.updaters.push(built.update);
      if (o.motion) this.motionTargets.push({ obj, motion: o.motion, basePos: obj.position.clone(), baseRot: obj.rotation.clone() });
    }

    this.scene = scene; this.camera = camera;
    this.renderer.toneMappingExposure = env.exposure ?? 1.1;

    // Post pipeline: scene -> bloom -> grain/vignette -> ACES+sRGB output.
    const composer = new EffectComposer(this.renderer);
    composer.addPass(new RenderPass(scene, camera));
    const b = env.bloom || {};
    const bloom = new UnrealBloomPass(new THREE.Vector2(this._w, this._h),
      b.strength ?? 0.85, b.radius ?? 0.6, b.threshold ?? 0.0);
    composer.addPass(bloom);
    const grain = new ShaderPass(GrainVignetteShader);
    grain.uniforms.uGrain.value = env.grain ?? 0.045;
    grain.uniforms.uVignette.value = env.vignette ?? 0.55;
    composer.addPass(grain);
    composer.addPass(new OutputPass());
    composer.setSize(this._w, this._h);
    this.composer = composer; this.bloom = bloom; this.grainPass = grain;
  }

  render(t) {
    if (!this.composer || !this.scene || !this.camera) return;
    for (const u of this.updaters) u(t);
    for (const mt of this.motionTargets) {
      const m = evalMotion(mt.motion, t);
      mt.obj.position.set(m.px ?? mt.basePos.x, m.py ?? mt.basePos.y, m.pz ?? mt.basePos.z);
      mt.obj.rotation.set(m.rx ?? mt.baseRot.x, m.ry ?? mt.baseRot.y, m.rz ?? mt.baseRot.z);
      if (m.scale != null) mt.obj.scale.setScalar(m.scale);
    }
    if (this.camMotion) {
      const m = evalMotion(this.camMotion, t);
      this.camera.position.set(m.px ?? this.camBasePos[0], m.py ?? this.camBasePos[1], m.pz ?? this.camBasePos[2]);
      this.camera.lookAt(m.lx ?? this.camLookAt[0], m.ly ?? this.camLookAt[1], m.lz ?? this.camLookAt[2]);
    }
    if (this.grainPass) this.grainPass.uniforms.uTime.value = t * 0.001;
    this.composer.render();
  }

  // Live-tune environment without rebuilding geometry (editor use).
  applyEnvironment(env) {
    if (!this.scene) return;
    env = env || {};
    this.renderer.toneMappingExposure = env.exposure ?? 1.1;
    if (this.bloom) {
      const b = env.bloom || {};
      if (b.strength != null) this.bloom.strength = b.strength;
      if (b.radius != null) this.bloom.radius = b.radius;
      if (b.threshold != null) this.bloom.threshold = b.threshold;
    }
    if (this.grainPass) {
      if (env.grain != null) this.grainPass.uniforms.uGrain.value = env.grain;
      if (env.vignette != null) this.grainPass.uniforms.uVignette.value = env.vignette;
    }
    if (env.background && this.scene.background) this.scene.background.set(env.background);
    if (env.fog) {
      if (!this.scene.fog) this.scene.fog = new THREE.Fog(new THREE.Color(env.fog.color || '#000'), env.fog.near ?? 10, env.fog.far ?? 80);
      else { this.scene.fog.color.set(env.fog.color || '#000'); this.scene.fog.near = env.fog.near ?? this.scene.fog.near; this.scene.fog.far = env.fog.far ?? this.scene.fog.far; }
    } else { this.scene.fog = null; }
  }

  // Live-tune camera without rebuilding (editor use).
  applyCamera(cam) {
    if (!this.camera || !cam) return;
    if (cam.fov != null) { this.camera.fov = cam.fov; this.camera.updateProjectionMatrix(); }
    if (cam.position) { this.camBasePos = cam.position.slice(); if (!this.camMotion) this.camera.position.set(...cam.position); }
    if (cam.lookAt) { this.camLookAt = cam.lookAt.slice(); if (!this.camMotion) this.camera.lookAt(...cam.lookAt); }
    if ('motion' in cam) this.camMotion = cam.motion || null;
  }

  _disposeScene() {
    if (this.scene) {
      this.scene.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
        if (o.material) { const ms = Array.isArray(o.material) ? o.material : [o.material]; for (const m of ms) m.dispose(); }
      });
      this.scene = null;
    }
    if (this.composer) { this.composer.dispose(); this.composer = null; }
    this.updaters = []; this.motionTargets = [];
  }

  clear() { this._disposeScene(); this.renderer.clear(); }
}
