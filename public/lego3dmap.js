/*
  LegoLog collection map — every owned set laid out on one floor, explorable
  with a free-roam (WASD + mouse-look) camera. Builds on the same
  three.js/LDrawLoader foundation as lego3d.js's single-set viewer (see that
  file's header comment for the CDN/dependency tradeoffs, which apply here
  too) but renders many models into one scene instead of one at a time, with
  a shared LDrawLoader/material cache so common parts across sets are only
  fetched once.

  Sets without an LDraw model (the common case — see design/3D_VIEWER.md)
  show as a photo card standing in their grid slot instead of empty space,
  so the whole collection is represented even though most sets won't have a
  real 3D model.
*/
import * as THREE from './vendor/three/three.module.min.js';
import { LDrawLoader } from './vendor/three/LDrawLoader.js';
import { PointerLockControls } from './vendor/three/PointerLockControls.js';
import { CSS2DRenderer, CSS2DObject } from './vendor/three/CSS2DRenderer.js';

const PARTS_LIBRARY_BASE = 'https://raw.githubusercontent.com/gkjohnson/ldraw-parts-library/master/complete/ldraw/';
// LDraw units between grid slots. Generous for small/medium sets; a very
// large set (e.g. a 1000+ piece model) can outgrow one cell and overlap its
// neighbors slightly — packing slot size to each model's real footprint
// would need loading before layout, which would delay first paint. Known
// v1 limitation, not fixed.
const CELL_SIZE = 500;
const MOVE_SPEED = 260; // LDraw units / second

let scene, camera, renderer, labelRenderer, controls, animId, resizeObserver, clock, loader;
const keys = Object.create(null);

const MOVE_KEYS = new Set(['Space', 'KeyW', 'KeyA', 'KeyS', 'KeyD']);
function onKeyDown(e) {
  keys[e.code] = true;
  if (controls?.isLocked && MOVE_KEYS.has(e.code)) e.preventDefault(); // no page-scroll-on-Space while exploring
}
function onKeyUp(e) { keys[e.code] = false; }

export function disposeMap() {
  if (animId != null) cancelAnimationFrame(animId);
  if (resizeObserver) resizeObserver.disconnect();
  document.removeEventListener('keydown', onKeyDown);
  document.removeEventListener('keyup', onKeyUp);
  try { controls?.unlock(); } catch { /* not locked */ }
  controls?.dispose?.();
  if (renderer) { renderer.dispose(); renderer.domElement?.remove(); }
  labelRenderer?.domElement?.remove();
  scene = camera = renderer = labelRenderer = controls = animId = resizeObserver = clock = loader = null;
}

function gridSlot(index, cols) {
  const row = Math.floor(index / cols);
  const col = index % cols;
  return { x: (col - (cols - 1) / 2) * CELL_SIZE, z: (row - (cols - 1) / 2) * CELL_SIZE };
}

function makeLabel(text) {
  const div = document.createElement('div');
  div.textContent = text;
  div.style.cssText =
    'font:600 12px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e2e8f0;' +
    'background:rgb(15 23 42 / .78);padding:3px 9px;border-radius:9999px;white-space:nowrap;';
  return new CSS2DObject(div);
}

function makePlaceholderCard(item) {
  const group = new THREE.Group();
  const cardMat = new THREE.MeshBasicMaterial({ color: 0x1e293b, side: THREE.DoubleSide });
  const card = new THREE.Mesh(new THREE.PlaneGeometry(160, 160), cardMat);
  card.position.y = 90;
  const stand = new THREE.Mesh(
    new THREE.BoxGeometry(20, 8, 20),
    new THREE.MeshStandardMaterial({ color: 0x334155 })
  );
  stand.position.y = 4;
  group.add(card, stand);

  if (item.imgUrl) {
    new THREE.TextureLoader().load(
      item.imgUrl,
      (tex) => { tex.colorSpace = THREE.SRGBColorSpace; cardMat.map = tex; cardMat.needsUpdate = true; },
      undefined,
      () => { /* texture failed (CORS, 404, ...) — card stays a plain color, never breaks the scene */ }
    );
  }
  return group;
}

function frameModel(group) {
  const box = new THREE.Box3().setFromObject(group);
  const size = box.getSize(new THREE.Vector3());
  const finite = [size.x, size.y, size.z].every(Number.isFinite) && Math.max(size.x, size.y, size.z) > 0;
  return finite ? size : new THREE.Vector3(160, 160, 160);
}

/**
 * @param items [{ setNum, name, imgUrl, modelFileUrl: string|null }]
 * @param opts.onSetSettled(setNum, hasRealModel) — called once per item, whether
 *   it upgraded to a real model or fell back to the placeholder card
 * @param opts.onLockChange(isLocked) — pointer-lock state, for an instructional overlay
 */
export async function renderCollectionMap(container, items, { onSetSettled, onLockChange } = {}) {
  disposeMap();
  container.replaceChildren();
  container.style.position = 'relative';
  clock = new THREE.Clock();

  const width = container.clientWidth || 1;
  const height = container.clientHeight || 1;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f172a);
  scene.fog = new THREE.Fog(0x0f172a, 900, 4200);

  camera = new THREE.PerspectiveCamera(60, width / height, 1, 20000);
  camera.position.set(0, 220, CELL_SIZE);

  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);

  labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(width, height);
  labelRenderer.domElement.style.cssText = 'position:absolute; inset:0; pointer-events:none;';
  container.appendChild(labelRenderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  const sun = new THREE.DirectionalLight(0xffffff, 1);
  sun.position.set(500, 900, 400);
  scene.add(sun);

  const cols = Math.max(1, Math.ceil(Math.sqrt(items.length)));
  const floorSize = (cols + 1) * CELL_SIZE;
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(floorSize, floorSize),
    new THREE.MeshStandardMaterial({ color: 0x1e293b })
  );
  floor.rotation.x = -Math.PI / 2;
  scene.add(floor);
  scene.add(new THREE.GridHelper(floorSize, cols + 1, 0x475569, 0x1e293b));

  controls = new PointerLockControls(camera, renderer.domElement);
  renderer.domElement.addEventListener('click', () => controls.lock());
  controls.addEventListener('lock', () => onLockChange?.(true));
  controls.addEventListener('unlock', () => onLockChange?.(false));
  document.addEventListener('keydown', onKeyDown);
  document.addEventListener('keyup', onKeyUp);

  // Placeholders go up immediately — they only need each set's product photo
  // (already loading elsewhere in the app, and non-blocking here via the
  // TextureLoader callback below), not the network-dependent LDraw parts
  // pipeline. The scene is fully explorable before a single brick model has
  // loaded; real models swap in over the placeholders as they arrive.
  items.forEach((item, i) => {
    const { x, z } = gridSlot(i, cols);
    const placeholder = makePlaceholderCard(item);
    placeholder.position.set(x, 0, z);
    const placeholderLabel = makeLabel(item.name);
    placeholderLabel.position.set(0, 190, 0);
    placeholder.add(placeholderLabel);
    scene.add(placeholder);
    item._slot = { x, z, placeholder };
  });

  const tick = () => {
    animId = requestAnimationFrame(tick);
    const dt = Math.min(clock.getDelta(), 0.1);
    if (controls.isLocked) {
      const step = MOVE_SPEED * dt;
      if (keys.KeyW) controls.moveForward(step);
      if (keys.KeyS) controls.moveForward(-step);
      if (keys.KeyD) controls.moveRight(step);
      if (keys.KeyA) controls.moveRight(-step);
      if (keys.Space) camera.position.y += step;
      if (keys.ShiftLeft || keys.ShiftRight) camera.position.y -= step;
      camera.position.y = Math.max(20, camera.position.y);
    }
    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);
  };
  tick();

  resizeObserver = new ResizeObserver(() => {
    if (!renderer || !container.clientWidth || !container.clientHeight) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
    labelRenderer.setSize(container.clientWidth, container.clientHeight);
  });
  resizeObserver.observe(container);

  loadRealModels(items.filter((it) => it.modelFileUrl), onSetSettled);
}

// Runs after the scene is already up and explorable — a slow or hung parts-
// library fetch (see design/3D_VIEWER.md) delays models popping in, never
// delays the map itself being visible.
async function loadRealModels(modeled, onSetSettled) {
  if (!modeled.length) return;
  const activeLoader = (loader = new LDrawLoader());
  activeLoader.setPartsLibraryPath(PARTS_LIBRARY_BASE);
  await activeLoader.preloadMaterials(PARTS_LIBRARY_BASE + 'LDConfig.ldr').catch(() => {});
  if (loader !== activeLoader) return; // map was disposed/rebuilt while this was in flight

  modeled.forEach((item) => {
    activeLoader.loadAsync(item.modelFileUrl)
      .then((group) => {
        if (loader !== activeLoader || !item._slot) return;
        const { x, z, placeholder } = item._slot;
        const size = frameModel(group);
        const scale = Math.min(1, (CELL_SIZE * 0.72) / Math.max(size.x, size.z));
        group.scale.setScalar(scale);
        group.rotation.x = Math.PI; // LDraw's Y axis points down
        group.position.set(x, 0, z);
        const modelLabel = makeLabel(item.name);
        modelLabel.position.set(0, size.y * scale + 24, 0);
        group.add(modelLabel);
        scene.remove(placeholder);
        scene.add(group);
        onSetSettled?.(item.setNum, true);
      })
      .catch(() => onSetSettled?.(item.setNum, false));
  });
}
