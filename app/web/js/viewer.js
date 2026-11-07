// 3D表示（three.js）。Flutterからは window.jijoguViewer を dart:js_interop で呼ぶ。
// docs/architecture.md「three.js ビューア」
import * as THREE from 'three';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const views = new WeakMap();

function setup(el) {
  if (views.has(el)) return views.get(el);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  el.style.touchAction = 'none';
  el.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6));
  const dir = new THREE.DirectionalLight(0xffffff, 1.4);
  dir.position.set(80, 120, 100);
  scene.add(dir);
  const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  const group = new THREE.Group();
  group.rotation.x = -Math.PI / 2; // OpenSCAD は Z が上、three.js は Y が上
  scene.add(group);
  const state = { renderer, scene, camera, controls, group, meshes: [] };
  const resize = () => {
    const w = el.clientWidth || 300, h = el.clientHeight || 300;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(el);
  resize();
  const loop = () => { controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop); };
  loop();
  views.set(el, state);
  return state;
}

function clear(state) {
  for (const m of state.meshes) { state.group.remove(m); m.geometry?.dispose(); }
  state.meshes = [];
}

function frame(state) {
  const box = new THREE.Box3().setFromObject(state.group);
  const size = box.getSize(new THREE.Vector3()).length();
  const center = box.getCenter(new THREE.Vector3());
  state.controls.target.copy(center);
  // 全体が収まる距離。縦長の画面（スマホ）では横の画角が狭いので、そのぶん離す
  const fov = (state.camera.fov * Math.PI) / 180;
  const dist = (size / 2 / Math.tan(fov / 2)) * 1.15 / Math.min(1, state.camera.aspect);
  const dir = new THREE.Vector3(0.62, 0.4, 0.8).normalize();
  state.camera.position.copy(center).add(dir.multiplyScalar(dist));
  state.camera.near = size / 100;
  state.camera.far = size * 20;
  state.camera.updateProjectionMatrix();
}

function capsuleMesh(p1, p2, r, material) {
  const a = new THREE.Vector3(...p1), b = new THREE.Vector3(...p2);
  const len = a.distanceTo(b);
  const geo = new THREE.CapsuleGeometry(r, len, 8, 16);
  const mesh = new THREE.Mesh(geo, material);
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
  return mesh;
}

const skin = () => new THREE.MeshStandardMaterial({ color: 0xf2c09e, transparent: true, opacity: 0.45, depthWrite: false });

window.jijoguViewer = {
  // 握りのSTL。capsulesJson は握りの座標系のカプセル（[[x1,y1,z1,x2,y2,z2,r], ...]）
  showStl(el, url, color, capsulesJson, hand) {
    const state = setup(el);
    clear(state);
    new STLLoader().load(url, (geo) => {
      geo.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.05 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.userData.main = true;
      state.group.add(mesh);
      state.meshes.push(mesh);
      const caps = JSON.parse(capsulesJson || '[]');
      const sx = hand === 'left' ? -1 : 1;
      for (const c of caps) {
        const m = capsuleMesh([sx * c[0], c[1], c[2]], [sx * c[3], c[4], c[5]], c[6], skin());
        state.group.add(m);
        state.meshes.push(m);
      }
      frame(state);
    });
  },
  setColor(el, color) {
    const state = views.get(el);
    if (!state) return;
    for (const m of state.meshes) if (m.userData.main) m.material.color.set(color);
  },
  // 手のカプセルモデル（手の座標系）と、すき間の円
  showHand(el, handModelJson) {
    const state = setup(el);
    clear(state);
    const hm = JSON.parse(handModelJson);
    for (const c of hm.capsules) {
      const m = capsuleMesh(c.p1_mm, c.p2_mm, c.radius_mm,
        new THREE.MeshStandardMaterial({ color: 0xf2c09e, roughness: 0.8 }));
      state.group.add(m);
      state.meshes.push(m);
    }
    // 手のひら（手首から付け根までの板）
    const palm = new THREE.Mesh(new THREE.BoxGeometry(70, 95, 6),
      new THREE.MeshStandardMaterial({ color: 0xe9b48f, roughness: 0.9 }));
    palm.position.set(4, 45, -3);
    state.group.add(palm);
    state.meshes.push(palm);
    for (const [name, cav] of Object.entries(hm.cavities)) {
      if (!cav.center_mm) continue;
      const ring = new THREE.Mesh(new THREE.TorusGeometry(cav.diameter_mm / 2, 0.8, 8, 48),
        new THREE.MeshStandardMaterial({ color: name === 'index' || name === 'pinky' ? 0x2f7d6d : 0x7fb8aa }));
      ring.position.set(...cav.center_mm);
      ring.rotation.y = Math.PI / 2; // 指の曲がる面（x にほぼ垂直）に置く
      state.group.add(ring);
      state.meshes.push(ring);
    }
    frame(state);
  },
};
window.dispatchEvent(new Event('jijogu-viewer-ready'));
