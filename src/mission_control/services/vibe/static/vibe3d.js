// Vibe 3D engine — experimental WebGL renderer for `renderer:"3d"` scenes.
//
// Parallel to the 2D canvas engine in display.html: a 3D scene is the same JSON
// envelope (id, name, MU/TH/UR metadata) but carries `camera`, `environment`,
// and an `objects[]` array instead of `layers[]`. Each object has a `type`
// dispatched to a builder below, optional `params`, and an optional `motion`
// block of expression strings evaluated per frame (same idea as the 2D motion
// evaluator). Everything is procedural — no external models or images — so it
// stays offline-safe inside the frozen .app and inside OBS (WebGL2/CEF).
//
// The engine owns its own <canvas>; display.html stacks it behind the 2D canvas
// and reuses the existing black-overlay crossfade, so scene transitions are
// uniform across 2D and 3D.

import * as THREE from './three.module.min.js';

const TAU = Math.PI * 2;

// ── Motion evaluator ──────────────────────────────────────────────────────
// Mirrors the 2D engine: math-only expressions of `t` (ms since start).
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

// ── Procedural textures (cached) ──────────────────────────────────────────
const _texCache = new Map();
function softSprite(inner = 'rgba(255,255,255,1)', outer = 'rgba(255,255,255,0)') {
  const key = inner + '|' + outer;
  if (_texCache.has(key)) return _texCache.get(key);
  const s = 128;
  const cv = document.createElement('canvas');
  cv.width = cv.height = s;
  const g = cv.getContext('2d');
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0, inner);
  grad.addColorStop(0.5, inner.replace(/[\d.]+\)$/, '0.35)'));
  grad.addColorStop(1, outer);
  g.fillStyle = grad;
  g.fillRect(0, 0, s, s);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  _texCache.set(key, tex);
  return tex;
}

function rand(a, b) { return a + Math.random() * (b - a); }

// ── Object builders ───────────────────────────────────────────────────────
// Each returns { object3d, update(t) } where update is optional intrinsic
// animation (rotation, pulsing). Engine applies `motion` transforms on top.
const BUILDERS = {

  // Sphere shell of stars; slow drift.
  starfield(p) {
    const count = Math.min(p.count ?? 1500, 6000);
    const radius = p.radius ?? 120;
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const u = Math.random(), v = Math.random();
      const theta = TAU * u, phi = Math.acos(2 * v - 1);
      const r = radius * (0.6 + 0.4 * Math.random());
      pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const mat = new THREE.PointsMaterial({
      size: p.size ?? 0.7, map: softSprite(p.color || 'rgba(180,200,230,1)'),
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      color: new THREE.Color(p.color || '#b4c8e6'),
    });
    const obj = new THREE.Points(geo, mat);
    const spin = p.spin ?? 0.000004;
    return { object3d: obj, update: (t) => { obj.rotation.y = t * spin; } };
  },

  // Billboarded additive cloud puffs — gas / nebula volume.
  nebula_volume(p) {
    const count = Math.min(p.count ?? 18, 80);
    const spread = p.spread ?? 30;
    const group = new THREE.Group();
    const tex = softSprite(p.color || 'rgba(120,30,60,1)');
    const sprites = [];
    for (let i = 0; i < count; i++) {
      const mat = new THREE.SpriteMaterial({
        map: tex, transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending, opacity: rand(p.alpha_min ?? 0.04, p.alpha_max ?? 0.14),
        color: new THREE.Color(p.color || '#781e3c'),
      });
      const s = new THREE.Sprite(mat);
      s.position.set(rand(-spread, spread), rand(-spread * 0.5, spread * 0.5), rand(-spread, spread));
      const sc = rand(p.size_min ?? 8, p.size_max ?? 26);
      s.scale.set(sc, sc, 1);
      s.userData.phase = Math.random() * TAU;
      s.userData.baseA = mat.opacity;
      group.add(s); sprites.push(s);
    }
    const drift = p.drift ?? 0.00002;
    return {
      object3d: group,
      update: (t) => {
        group.rotation.y = t * drift;
        for (const s of sprites) {
          s.material.opacity = s.userData.baseA * (0.6 + 0.4 * Math.sin(t * 0.0004 + s.userData.phase));
        }
      },
    };
  },

  // The set-piece: a dark core with a glowing accretion disk + halo. The
  // "heart of darkness".
  dark_core(p) {
    const group = new THREE.Group();
    const R = p.radius ?? 2.2;
    // Black event-horizon sphere.
    const core = new THREE.Mesh(
      new THREE.SphereGeometry(R, 48, 48),
      new THREE.MeshBasicMaterial({ color: 0x000000 }),
    );
    group.add(core);
    // Rim glow shell (backside additive).
    const halo = new THREE.Mesh(
      new THREE.SphereGeometry(R * 1.35, 48, 48),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color(p.glow || '#5a0c1e'),
        transparent: true, opacity: 0.5, side: THREE.BackSide,
        blending: THREE.AdditiveBlending, depthWrite: false,
      }),
    );
    group.add(halo);
    // Accretion disk — annulus of additive particles.
    const dcount = Math.min(p.disk_count ?? 2600, 8000);
    const inner = R * 1.2, outer = R * (p.disk_radius ?? 4.5);
    const pos = new Float32Array(dcount * 3);
    const col = new Float32Array(dcount * 3);
    const c1 = new THREE.Color(p.ring_color || '#ff3a2a');
    const c2 = new THREE.Color(p.ring_color2 || '#ffd089');
    for (let i = 0; i < dcount; i++) {
      const a = Math.random() * TAU;
      const rr = inner + Math.pow(Math.random(), 1.6) * (outer - inner);
      pos[i * 3]     = Math.cos(a) * rr;
      pos[i * 3 + 1] = rand(-0.06, 0.06) * rr;
      pos[i * 3 + 2] = Math.sin(a) * rr;
      const m = (rr - inner) / (outer - inner);
      const c = c1.clone().lerp(c2, Math.random() * 0.6 + m * 0.4);
      col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
    }
    const dgeo = new THREE.BufferGeometry();
    dgeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    dgeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    const disk = new THREE.Points(dgeo, new THREE.PointsMaterial({
      size: p.disk_dot ?? 0.18, map: softSprite(), vertexColors: true,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    disk.rotation.x = p.tilt ?? 1.15;
    group.add(disk);
    const spin = p.disk_spin ?? 0.00035;
    return {
      object3d: group,
      update: (t) => {
        disk.rotation.z = t * spin;
        halo.material.opacity = 0.4 + 0.12 * Math.sin(t * 0.0009);
      },
    };
  },

  // Standalone orbiting particle ring.
  accretion_disk(p) {
    return BUILDERS.dark_core({ ...p, radius: 0.001, glow: 'rgba(0,0,0,0)' });
  },

  // Tumbling wreckage chunks drifting in space.
  debris_field(p) {
    const count = Math.min(p.count ?? 40, 200);
    const spread = p.spread ?? 22;
    const group = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(p.color || '#3a3530'), roughness: 0.9, metalness: 0.3,
      emissive: new THREE.Color(p.emissive || '#0a0604'), emissiveIntensity: 0.4,
    });
    const geos = [
      new THREE.TetrahedronGeometry(1),
      new THREE.BoxGeometry(1.4, 0.6, 0.9),
      new THREE.IcosahedronGeometry(0.8, 0),
    ];
    const chunks = [];
    for (let i = 0; i < count; i++) {
      const m = new THREE.Mesh(geos[i % geos.length], mat);
      m.position.set(rand(-spread, spread), rand(-spread * 0.6, spread * 0.6), rand(-spread, spread));
      const sc = rand(p.size_min ?? 0.2, p.size_max ?? 1.1);
      m.scale.setScalar(sc);
      m.rotation.set(Math.random() * TAU, Math.random() * TAU, Math.random() * TAU);
      m.userData.rs = [rand(-0.0004, 0.0004), rand(-0.0004, 0.0004), rand(-0.0004, 0.0004)];
      group.add(m); chunks.push(m);
    }
    const drift = p.drift ?? 0.00001;
    return {
      object3d: group,
      update: (t) => {
        group.rotation.y = t * drift;
        for (const m of chunks) {
          m.rotation.x += m.userData.rs[0]; m.rotation.y += m.userData.rs[1]; m.rotation.z += m.userData.rs[2];
        }
      },
    };
  },

  // A wrecked hull built from primitives — slowly tumbling derelict.
  derelict_hull(p) {
    const group = new THREE.Group();
    const skin = new THREE.MeshStandardMaterial({
      color: new THREE.Color(p.color || '#2b2622'), roughness: 0.85, metalness: 0.4,
      emissive: new THREE.Color('#060403'), emissiveIntensity: 0.5,
    });
    const hull = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.9, 7, 12), skin);
    hull.rotation.z = Math.PI / 2;
    group.add(hull);
    const spine = new THREE.Mesh(new THREE.BoxGeometry(5, 0.4, 0.4), skin);
    group.add(spine);
    for (const sx of [-1.6, 1.6]) {
      const wing = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.15, 3.4), skin);
      wing.position.set(sx, 0, 0);
      group.add(wing);
    }
    // Faint emergency window lights.
    const lit = new THREE.Color(p.lights || '#ff5522');
    for (let i = 0; i < 8; i++) {
      const dot = new THREE.Mesh(
        new THREE.SphereGeometry(0.07, 6, 6),
        new THREE.MeshBasicMaterial({ color: lit, transparent: true, opacity: rand(0.4, 0.9) }),
      );
      dot.position.set(rand(-3, 3), rand(-0.4, 0.4), 0.55);
      group.add(dot);
    }
    const sc = p.scale ?? 1;
    group.scale.setScalar(sc);
    const tx = p.tumble ?? 0.00003, ty = p.tumble_y ?? 0.00005;
    return {
      object3d: group,
      update: (t) => { group.rotation.x = t * tx; group.rotation.y = t * ty; },
    };
  },

  // Near-camera drifting dust for depth.
  dust_motes(p) {
    const count = Math.min(p.count ?? 400, 2000);
    const spread = p.spread ?? 40;
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3]     = rand(-spread, spread);
      pos[i * 3 + 1] = rand(-spread, spread);
      pos[i * 3 + 2] = rand(-spread, spread);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const obj = new THREE.Points(geo, new THREE.PointsMaterial({
      size: p.size ?? 0.12, map: softSprite(p.color || 'rgba(150,140,130,1)'),
      transparent: true, opacity: p.opacity ?? 0.5, depthWrite: false,
      blending: THREE.AdditiveBlending, color: new THREE.Color(p.color || '#968c82'),
    }));
    const drift = p.drift ?? 0.00002;
    return { object3d: obj, update: (t) => { obj.rotation.x = t * drift; obj.rotation.z = t * drift * 0.6; } };
  },

  // Lights (point / ambient). Unlit materials ignore these; hull/debris use them.
  light(p) {
    let l;
    if ((p.kind || 'point') === 'ambient') {
      l = new THREE.AmbientLight(new THREE.Color(p.color || '#ffffff'), p.intensity ?? 0.5);
    } else {
      l = new THREE.PointLight(new THREE.Color(p.color || '#ff6633'), p.intensity ?? 60, p.distance ?? 0, 2);
      const pp = p.position || [0, 0, 0];
      l.position.set(pp[0], pp[1], pp[2]);
    }
    return { object3d: l };
  },

  // Receding wireframe grid — sensor / neural-map vibe.
  grid(p) {
    const g = new THREE.GridHelper(p.size ?? 80, p.divisions ?? 40,
      new THREE.Color(p.color || '#1e6e3c'), new THREE.Color(p.color || '#0e3a20'));
    g.material.transparent = true; g.material.opacity = p.opacity ?? 0.25;
    g.position.y = p.y ?? -6;
    return { object3d: g };
  },
};

// ── Engine ────────────────────────────────────────────────────────────────
export class Vibe3DEngine {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.scene = null;
    this.camera = null;
    this.updaters = [];
    this.motionTargets = []; // { obj, motion, basePos, baseRot }
    this.camMotion = null;
    this.camBasePos = [0, 0, 12];
    this.camLookAt = [0, 0, 0];
  }

  resize(w, h) {
    this.renderer.setSize(w, h, false);
    if (this.camera) { this.camera.aspect = w / h; this.camera.updateProjectionMatrix(); }
  }

  load(def) {
    this._disposeScene();
    const scene = new THREE.Scene();
    const env = def.environment || {};
    scene.background = new THREE.Color(env.background || '#000000');
    if (env.fog) scene.fog = new THREE.Fog(new THREE.Color(env.fog.color || '#000000'), env.fog.near ?? 10, env.fog.far ?? 80);

    const cam = def.camera || {};
    const camera = new THREE.PerspectiveCamera(cam.fov ?? 60, 1, 0.1, 2000);
    this.camBasePos = cam.position || [0, 0, 12];
    this.camLookAt = cam.lookAt || [0, 0, 0];
    camera.position.set(...this.camBasePos);
    camera.lookAt(...this.camLookAt);
    this.camMotion = cam.motion || null;

    // Always provide a soft ambient so lit materials are never pure black.
    scene.add(new THREE.AmbientLight(0xffffff, 0.25));

    this.updaters = [];
    this.motionTargets = [];
    for (const o of (def.objects || [])) {
      const build = BUILDERS[o.type];
      if (!build) continue;
      let built;
      try { built = build(o.params || {}); } catch (_) { continue; }
      const obj = built.object3d;
      const pp = (o.params && o.params.position) || null;
      const rr = (o.params && o.params.rotation) || null;
      if (pp) obj.position.set(pp[0], pp[1], pp[2]);
      if (rr) obj.rotation.set(rr[0], rr[1], rr[2]);
      scene.add(obj);
      if (built.update) this.updaters.push(built.update);
      if (o.motion) this.motionTargets.push({
        obj, motion: o.motion,
        basePos: obj.position.clone(), baseRot: obj.rotation.clone(),
      });
    }

    this.scene = scene;
    this.camera = camera;
  }

  render(t) {
    if (!this.scene || !this.camera) return;
    for (const u of this.updaters) u(t);
    // Per-object motion (replaces axes the expression provides).
    for (const mt of this.motionTargets) {
      const m = evalMotion(mt.motion, t);
      mt.obj.position.set(
        m.px ?? mt.basePos.x, m.py ?? mt.basePos.y, m.pz ?? mt.basePos.z);
      mt.obj.rotation.set(
        m.rx ?? mt.baseRot.x, m.ry ?? mt.baseRot.y, m.rz ?? mt.baseRot.z);
      if (m.scale != null) mt.obj.scale.setScalar(m.scale);
    }
    // Camera motion.
    if (this.camMotion) {
      const m = evalMotion(this.camMotion, t);
      this.camera.position.set(
        m.px ?? this.camBasePos[0], m.py ?? this.camBasePos[1], m.pz ?? this.camBasePos[2]);
      this.camera.lookAt(
        m.lx ?? this.camLookAt[0], m.ly ?? this.camLookAt[1], m.lz ?? this.camLookAt[2]);
    }
    this.renderer.render(this.scene, this.camera);
  }

  _disposeScene() {
    if (!this.scene) return;
    this.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const mt of mats) mt.dispose();
      }
    });
    this.scene = null;
    this.updaters = [];
    this.motionTargets = [];
  }

  clear() { this._disposeScene(); this.renderer.clear(); }
}
