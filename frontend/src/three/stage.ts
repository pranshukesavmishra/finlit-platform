import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { markNo3d } from "./support";

export type Pointer = { x: number; y: number };   // -1..1 across the canvas, 0 at rest
export type Palette = { gold: THREE.Color; deep: THREE.Color; ink: THREE.Color; paper: THREE.Color; gain: THREE.Color; loss: THREE.Color; light: boolean };
export type Stage = { scene: THREE.Scene; camera: THREE.PerspectiveCamera; renderer: THREE.WebGLRenderer; palette: Palette; track(o: { dispose(): void }): void };
/** `p` is how far the viewer has dragged the scene (0 at rest); it only changes while the pointer is pressed on the canvas, so moving the mouse
 *  over a chart never turns it. `hover` is where the pointer is over the canvas, or null when it is elsewhere. */
export type Scene = { frame(t: number, dt: number, p: Pointer, hover: Pointer | null): void; recolor?(pal: Palette): void };

/** Colours for a scene, read where the canvas sits: a dark hero band can set --scene-paper and --scene-light: 0 so the scene matches the band
 *  rather than the page around it. */
export function readPalette(el: Element = document.documentElement): Palette {
  const cs = getComputedStyle(el), root = getComputedStyle(document.documentElement);
  const css = (n: string, f: string) => cs.getPropertyValue(n).trim() || root.getPropertyValue(n).trim() || f;
  const flag = cs.getPropertyValue("--scene-light").trim();
  const light = flag ? flag === "1" : document.documentElement.getAttribute("data-theme") === "light";
  return { gold: new THREE.Color(css("--gold", "#C9A24E")), deep: new THREE.Color(light ? "#8A6A25" : "#A8843A"), ink: new THREE.Color(light ? "#2E2A20" : "#EDE6D3"),
           paper: new THREE.Color(css("--scene-paper", "") || css("--bg", light ? "#F6F1E7" : "#0F0E0B")), gain: new THREE.Color("#2F7A58"), loss: new THREE.Color("#A8392F"), light };
}

/** Everything a scene needs to live inside a canvas: renderer, camera, soft studio reflections, and a loop that runs only while the canvas is on
 *  screen and the tab is visible. Reduced-motion visitors get one still frame. Returns a function that frees all GPU memory. */
export function mountStage(canvas: HTMLCanvasElement, build: (s: Stage) => Scene, opts: { fov?: number; maxDpr?: number } = {}): () => void {
  // A browser can report WebGL and still fail to start it (GPU blocked, driver blacklisted, context lost, software rendering).
  // Then the scene is simply left out: the page around it is complete without it and must never break.
  try { return mountStageOrThrow(canvas, build, opts); }
  catch (e) { console.warn("3D scene left out:", e instanceof Error ? e.message : e); markNo3d(); canvas.style.display = "none"; return () => undefined; }
}

function mountStageOrThrow(canvas: HTMLCanvasElement, build: (s: Stage) => Scene, opts: { fov?: number; maxDpr?: number }): () => void {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(opts.fov ?? 40, 1, 0.1, 200);
  const owned: { dispose(): void }[] = [];
  const pmrem = new THREE.PMREMGenerator(renderer);
  const env = pmrem.fromScene(new RoomEnvironment(), 0.04); scene.environment = env.texture; owned.push(env, pmrem);
  const stage: Stage = { scene, camera, renderer, palette: readPalette(canvas), track: (o) => owned.push(o) };
  const world = build(stage);

  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pointer: Pointer = { x: 0, y: 0 }, target: Pointer = { x: 0, y: 0 };
  let hover: Pointer | null = null, drag: { x: number; y: number } | null = null;
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
    world.frame(now / 1000, dt, pointer, hover); renderer.render(scene, camera);
    if (!calm && visible && !document.hidden) raf = requestAnimationFrame(draw);
  };
  const kick = () => { if (!raf && alive) { last = performance.now(); raf = requestAnimationFrame(draw); } };
  const ro = new ResizeObserver(() => { resize(); if (calm) kick(); }); ro.observe(canvas); resize();
  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) kick(); }); io.observe(canvas);
  const vis = () => { if (!document.hidden) kick(); }; document.addEventListener("visibilitychange", vis);
  const at = (e: PointerEvent): Pointer => { const r = canvas.getBoundingClientRect(); return { x: ((e.clientX - r.left) / r.width) * 2 - 1, y: ((e.clientY - r.top) / r.height) * 2 - 1 }; };
  const move = (e: PointerEvent) => {
    hover = at(e);
    if (drag) { const r = canvas.getBoundingClientRect(); target.x = Math.max(-1.5, Math.min(1.5, target.x + ((e.clientX - drag.x) / r.width) * 3)); target.y = Math.max(-0.8, Math.min(0.8, target.y + ((e.clientY - drag.y) / r.height) * 2)); drag = { x: e.clientX, y: e.clientY }; }
    if (calm || drag || hover) kick();
  };
  const down = (e: PointerEvent) => { if (e.button !== 0) return; drag = { x: e.clientX, y: e.clientY }; canvas.setPointerCapture?.(e.pointerId); canvas.style.cursor = "grabbing"; };
  const up = (e: PointerEvent) => { drag = null; canvas.style.cursor = ""; try { canvas.releasePointerCapture?.(e.pointerId); } catch { /* not captured */ } };
  const leave = () => { hover = null; if (calm) kick(); };
  canvas.style.touchAction = "pan-y";
  canvas.addEventListener("pointermove", move); canvas.addEventListener("pointerdown", down); canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up); canvas.addEventListener("pointerleave", leave);
  const theme = new MutationObserver(() => { stage.palette = readPalette(canvas); world.recolor?.(stage.palette); if (calm) kick(); });
  theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const lost = (e: Event) => { e.preventDefault(); alive = false; };
  canvas.addEventListener("webglcontextlost", lost);
  kick();

  return () => {
    alive = false; cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); theme.disconnect();
    document.removeEventListener("visibilitychange", vis); canvas.removeEventListener("pointermove", move); canvas.removeEventListener("pointerdown", down); canvas.removeEventListener("pointerup", up); canvas.removeEventListener("pointercancel", up); canvas.removeEventListener("pointerleave", leave); canvas.removeEventListener("webglcontextlost", lost);
    scene.traverse((o) => { const m = o as THREE.Mesh; if (m.geometry) m.geometry.dispose(); const mat = m.material as THREE.Material | THREE.Material[] | undefined; (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => { (x as THREE.MeshStandardMaterial).map?.dispose(); x.dispose(); }); });
    owned.forEach((o) => o.dispose()); renderer.dispose(); renderer.forceContextLoss();
  };
}
