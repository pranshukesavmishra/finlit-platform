import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

export type Pointer = { x: number; y: number };   // -1..1 across the canvas, 0 at rest
export type Palette = { gold: THREE.Color; deep: THREE.Color; ink: THREE.Color; paper: THREE.Color; gain: THREE.Color; loss: THREE.Color; light: boolean };
export type Stage = { scene: THREE.Scene; camera: THREE.PerspectiveCamera; renderer: THREE.WebGLRenderer; palette: Palette; track(o: { dispose(): void }): void };
export type Scene = { frame(t: number, dt: number, p: Pointer): void; recolor?(pal: Palette): void };

const css = (n: string, f: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f;
export function readPalette(): Palette {
  const light = document.documentElement.getAttribute("data-theme") === "light";
  return { gold: new THREE.Color(css("--gold", "#C9A24E")), deep: new THREE.Color(light ? "#8A6A25" : "#A8843A"), ink: new THREE.Color(light ? "#2E2A20" : "#EDE6D3"),
           paper: new THREE.Color(css("--bg", light ? "#F6F1E7" : "#0F0E0B")), gain: new THREE.Color("#2F7A58"), loss: new THREE.Color("#A8392F"), light };
}

/** Everything a scene needs to live inside a canvas: renderer, camera, soft studio reflections, and a loop that runs only while the canvas is on
 *  screen and the tab is visible. Reduced-motion visitors get one still frame. Returns a function that frees all GPU memory. */
export function mountStage(canvas: HTMLCanvasElement, build: (s: Stage) => Scene, opts: { fov?: number; maxDpr?: number } = {}): () => void {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(opts.fov ?? 40, 1, 0.1, 200);
  const owned: { dispose(): void }[] = [];
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = pmrem.fromScene(new RoomEnvironment(), 0.04); scene.environment = env.texture; owned.push(env, pmrem);
  const stage: Stage = { scene, camera, renderer, palette: readPalette(), track: (o) => owned.push(o) };
  const world = build(stage);

  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pointer: Pointer = { x: 0, y: 0 }, target: Pointer = { x: 0, y: 0 };
  let raf = 0, last = performance.now(), visible = true, alive = true;
  const resize = () => {
    const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, opts.maxDpr ?? 1.75)); renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  const draw = (now: number) => {
    raf = 0; if (!alive) return;
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    pointer.x += (target.x - pointer.x) * Math.min(1, dt * 4); pointer.y += (target.y - pointer.y) * Math.min(1, dt * 4);
    world.frame(now / 1000, dt, pointer); renderer.render(scene, camera);
    if (!calm && visible && !document.hidden) raf = requestAnimationFrame(draw);
  };
  const kick = () => { if (!raf && alive) { last = performance.now(); raf = requestAnimationFrame(draw); } };
  const ro = new ResizeObserver(() => { resize(); if (calm) kick(); }); ro.observe(canvas); resize();
  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) kick(); }); io.observe(canvas);
  const vis = () => { if (!document.hidden) kick(); }; document.addEventListener("visibilitychange", vis);
  const move = (e: PointerEvent) => { const r = canvas.getBoundingClientRect(); target.x = ((e.clientX - r.left) / r.width) * 2 - 1; target.y = ((e.clientY - r.top) / r.height) * 2 - 1; };
  if (!calm) window.addEventListener("pointermove", move, { passive: true });
  const theme = new MutationObserver(() => { stage.palette = readPalette(); world.recolor?.(stage.palette); if (calm) kick(); });
  theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const lost = (e: Event) => { e.preventDefault(); alive = false; };
  canvas.addEventListener("webglcontextlost", lost);
  kick();

  return () => {
    alive = false; cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); theme.disconnect();
    document.removeEventListener("visibilitychange", vis); window.removeEventListener("pointermove", move); canvas.removeEventListener("webglcontextlost", lost);
    scene.traverse((o) => { const m = o as THREE.Mesh; if (m.geometry) m.geometry.dispose(); const mat = m.material as THREE.Material | THREE.Material[] | undefined; (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => { (x as THREE.MeshStandardMaterial).map?.dispose(); x.dispose(); }); });
    owned.forEach((o) => o.dispose()); renderer.dispose(); renderer.forceContextLoss();
  };
}
