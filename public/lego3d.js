/*
  LegoLog 3D viewer — renders an LDraw model (.mpd/.ldr) in-browser via
  three.js + LDrawLoader (both vendored locally, see vendor/three/).

  Individual brick geometry isn't self-hosted (the full LDraw parts library
  is 100+ MB) — it's fetched on demand, per part actually used in a model,
  from a public static mirror of the LDraw parts library on GitHub. This is
  the one deliberate external-CDN dependency in the app: unlike the old
  Tailwind CDN it replaces elsewhere (design/WEBSITE_AUDIT.md's Critical
  finding), it's opt-in — only requested when a user opens a 3D view, never
  on page load — and failure degrades to an error message inside the modal,
  not a broken page.
*/
import * as THREE from './vendor/three/three.module.min.js';
import { LDrawLoader } from './vendor/three/LDrawLoader.js';
import { OrbitControls } from './vendor/three/OrbitControls.js';

const PARTS_LIBRARY_BASE = 'https://raw.githubusercontent.com/gkjohnson/ldraw-parts-library/master/complete/ldraw/';

let scene, camera, renderer, controls, animId, resizeObserver;

export function disposeViewer() {
  if (animId != null) cancelAnimationFrame(animId);
  if (resizeObserver) resizeObserver.disconnect();
  if (renderer) {
    renderer.dispose();
    renderer.domElement?.remove();
  }
  scene = camera = renderer = controls = animId = resizeObserver = null;
}

/**
 * Renders `fileUrl` (an LDraw .mpd/.ldr, same-origin — see the
 * /api/sets/{set_num}/ldraw-model/file proxy in app.py, which sidesteps
 * relying on the source host sending CORS headers for a page it wasn't
 * built to be fetched from) into `container`.
 */
export async function renderModel(container, fileUrl, { onProgress } = {}) {
  disposeViewer();
  container.replaceChildren();

  const width = container.clientWidth || 1;
  const height = container.clientHeight || 1;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f172a);

  camera = new THREE.PerspectiveCamera(45, width / height, 1, 100000);
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(200, -400, 300);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.4);
  fill.position.set(-200, 200, -300);
  scene.add(fill);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;

  const loader = new LDrawLoader();
  loader.setPartsLibraryPath(PARTS_LIBRARY_BASE);
  await loader.preloadMaterials(PARTS_LIBRARY_BASE + 'LDConfig.ldr');

  const group = await loader.loadAsync(fileUrl, onProgress);
  // LDraw's Y axis points down; flip so the model stands upright on screen.
  group.rotation.x = Math.PI;
  scene.add(group);

  const box = new THREE.Box3().setFromObject(group);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z) || 100;

  camera.position.set(center.x + maxDim * 0.9, center.y + maxDim * 0.7, center.z + maxDim * 0.9);
  camera.near = maxDim / 100;
  camera.far = maxDim * 20;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();

  const tick = () => {
    animId = requestAnimationFrame(tick);
    controls.update();
    renderer.render(scene, camera);
  };
  tick();

  resizeObserver = new ResizeObserver(() => {
    if (!renderer || !container.clientWidth || !container.clientHeight) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  });
  resizeObserver.observe(container);
}
