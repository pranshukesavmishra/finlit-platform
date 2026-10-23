import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { mountStage, type Palette, type Scene } from "./stage";

export type Plot3DSpec = { kind: "surface"; grid: (number | null)[][]; rowTicks: string[]; colTicks: string[]; rowTitle: string; colTitle: string; valueTitle: string; fmt: (v: number) => string; level?: number; levelName?: string; base?: [number, number] };

const W = 10, H = 3.6;
const nice = (lo: number, hi: number, n = 4) => Array.from({ length: n + 1 }, (_, k) => lo + ((hi - lo) * k) / n);

/** One labelled 3D plot for every chart kind: value scale on the back and side walls, a label on every axis, hover to read any bar, point or cell.
 *  Everything it draws is also in the flat chart or table it replaces; this only adds depth. */
export default function Plot3D({ spec, label }: { spec: Plot3DSpec; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [tip, setTip] = useState<string | null>(null);
  const fmtRef = useRef(spec.fmt);
  fmtRef.current = spec.fmt;
  const key = JSON.stringify(spec);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    return mountStage(cv, ({ scene, camera, palette, track }): Scene => {
      const fmt = (v: number) => fmtRef.current(v);
      scene.add(new THREE.AmbientLight(0xffffff, 0.75));
      const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(4, 9, 7); scene.add(sun);
      const group = new THREE.Group(); scene.add(group);
      const body = new THREE.Group(); group.add(body);          // data meshes: grows up from the zero line
      const recolors: ((pal: Palette) => void)[] = [];
      const hot: THREE.Object3D[] = [];

      // ---- labels: text drawn to a small canvas, always facing the viewer
      const texts: { s: THREE.Sprite; text: string; bold: boolean; faint: boolean }[] = [];
      const paint = (t: (typeof texts)[number], pal: Palette) => {
        const mat = t.s.material as THREE.SpriteMaterial, c = document.createElement("canvas"), g = c.getContext("2d")!;
        const font = `${t.bold ? 700 : 500} 40px IBM Plex Sans, system-ui, sans-serif`; g.font = font;
        c.width = Math.ceil(g.measureText(t.text).width) + 20; c.height = 64; g.font = font; g.textBaseline = "middle";
        g.fillStyle = "#" + (t.faint ? pal.ink.clone().lerp(pal.paper, 0.15) : pal.ink).getHexString(); g.fillText(t.text, 10, 34);
        mat.map?.dispose(); mat.map = new THREE.CanvasTexture(c); mat.map.colorSpace = THREE.SRGBColorSpace; mat.needsUpdate = true;
        t.s.userData.aspect = c.width / c.height;
      };
      const label = (text: string, x: number, y: number, z: number, o: { size?: number; bold?: boolean; faint?: boolean; ax?: number } = {}) => {
        const s = new THREE.Sprite(new THREE.SpriteMaterial({ transparent: true, depthTest: false })), t = { s, text, bold: !!o.bold, faint: !!o.faint };
        paint(t, palette); const h = o.size ?? 0.36; s.scale.set(h * s.userData.aspect, h, 1); s.center.set(o.ax ?? 0.5, 0.5); s.position.set(x, y, z); s.renderOrder = 10; group.add(s); texts.push(t);
      };
      const lines = (pts: number[], opacity: number) => {
        const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3)); track(g);
        const m = new THREE.LineBasicMaterial({ color: palette.ink, transparent: true, opacity }); track(m);
        const l = new THREE.LineSegments(g, m); group.add(l); recolors.push((p) => m.color.copy(p.ink)); return l;
      };
      /** the value scale: grid lines on the back and left walls, numbers at the left edge */
      const frame = (lo: number, hi: number, D: number, valueTitle?: string) => {
        const yOf = (v: number) => ((v - lo) / (hi - lo || 1)) * H, pts: number[] = [];
        nice(lo, hi).forEach((v) => {
          const y = yOf(v); pts.push(-W / 2, y, -D / 2, W / 2, y, -D / 2, -W / 2, y, -D / 2, -W / 2, y, D / 2);
          label(fmt(v), -W / 2 - 0.2, y, D / 2, { ax: 1, size: 0.36, faint: true });
        });
        pts.push(-W / 2, 0, D / 2, W / 2, 0, D / 2, W / 2, 0, D / 2, W / 2, 0, -D / 2);
        lines(pts, 0.28); if (valueTitle) label(valueTitle, -W / 2, H + 0.55, -D / 2, { ax: 0, bold: true, size: 0.36 });
        return yOf;
      };
      const ray = new THREE.Raycaster(), v2 = new THREE.Vector2();
      let hover: THREE.Object3D | null = null, shown: string | null = null, born = -1;
      const pointOn = (p: { x: number; y: number } | null) => { if (!p) return null; v2.set(p.x, -p.y); ray.setFromCamera(v2, camera); return ray.intersectObjects(hot, false)[0] ?? null; };
      let onHit: (h: THREE.Intersection | null) => string | null = () => null;

      if (spec.kind === "surface") {
        const R = spec.grid.length, C = spec.grid[0]?.length ?? 0, D = 6.4;
        const vals = spec.grid.flat().filter((v): v is number => v != null && isFinite(v));
        const lo = Math.min(0, ...vals, spec.level ?? 0), hi = Math.max(1e-9, ...vals, spec.level ?? 0) * 1.05, yOf = frame(lo, hi, D, spec.valueTitle), y0 = yOf(0), span = hi - lo || 1;
        body.position.y = y0;
        const geo = new THREE.PlaneGeometry(W, D, Math.max(1, C - 1), Math.max(1, R - 1)); geo.rotateX(-Math.PI / 2); track(geo);
        const pos = geo.attributes.position, col = new Float32Array(pos.count * 3);
        for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) pos.setY(r * C + c, yOf(spec.grid[r][c] ?? lo) - y0);
        geo.computeVertexNormals();
        const paintSurf = (pal: Palette) => { for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) { const v = spec.grid[r][c], i = r * C + c, t = v == null ? 0 : (v - lo) / span;
          const k = (spec.level != null ? (v != null && v >= spec.level ? pal.gain : pal.loss) : pal.gold).clone().multiplyScalar(0.7 + 0.5 * t); col[i * 3] = k.r; col[i * 3 + 1] = k.g; col[i * 3 + 2] = k.b; }
          geo.setAttribute("color", new THREE.BufferAttribute(col, 3)); };
        paintSurf(palette); recolors.push(paintSurf);
        const mat = new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.15, roughness: 0.55, side: THREE.DoubleSide, flatShading: true }); track(mat);
        const mesh = new THREE.Mesh(geo, mat); body.add(mesh); hot.push(mesh);
        const wm = new THREE.LineBasicMaterial({ color: palette.ink, transparent: true, opacity: 0.2 }); track(wm); recolors.push((p) => wm.color.copy(p.ink));
        const wire = new THREE.LineSegments(new THREE.WireframeGeometry(geo), wm); track(wire.geometry); body.add(wire);
        if (spec.level != null) {
          const sm = new THREE.MeshBasicMaterial({ color: palette.ink, transparent: true, opacity: 0.13, side: THREE.DoubleSide, depthWrite: false }); track(sm); recolors.push((p) => sm.color.copy(p.ink));
          const sheet = new THREE.Mesh(new THREE.PlaneGeometry(W + 0.4, D + 0.4), sm); track(sheet.geometry); sheet.rotation.x = -Math.PI / 2; sheet.position.y = yOf(spec.level) - y0; body.add(sheet);
          label(`${spec.levelName ?? "Today's price"} ${fmt(spec.level)}`, W / 2 + 0.3, yOf(spec.level), D / 2, { ax: 0, bold: true, size: 0.34 });
        }
        if (spec.base && spec.grid[spec.base[0]]?.[spec.base[1]] != null) {
          const [br, bc] = spec.base, ball = new THREE.Mesh(new THREE.SphereGeometry(0.22, 24, 16), new THREE.MeshStandardMaterial({ color: palette.ink, emissive: palette.gold, emissiveIntensity: 0.5 })); track(ball.geometry); track(ball.material as THREE.Material);
          ball.position.set((bc / Math.max(1, C - 1) - 0.5) * W, yOf(spec.grid[br][bc] as number) - y0 + 0.3, (br / Math.max(1, R - 1) - 0.5) * D); body.add(ball);
          label("Your base case", ball.position.x, yOf(spec.grid[br][bc] as number) + 0.85, ball.position.z, { bold: true, size: 0.34 });
        }
        spec.colTicks.forEach((t, c) => { if (C < 8 || c % 2 === 0) label(t, (c / Math.max(1, C - 1) - 0.5) * W, 0, D / 2 + 0.45, { size: 0.36, faint: true }); });
        spec.rowTicks.forEach((t, r) => label(t, W / 2 + 0.3, 0, (r / Math.max(1, R - 1) - 0.5) * D, { ax: 0, size: 0.36, faint: true }));
        label(spec.colTitle + " →", 0, 0, D / 2 + 1.0, { bold: true }); label(spec.rowTitle + " →", W / 2 + 1.9, 0, 0, { bold: true, ax: 0 });
        camera.position.set(0, 7.2, 13.5); camera.lookAt(0, 1.2, 0);
        onHit = (h) => { if (!h) return null; const q = mesh.worldToLocal(h.point.clone()), c = Math.round((q.x / W + 0.5) * (C - 1)), r = Math.round((q.z / D + 0.5) * (R - 1)), v = spec.grid[r]?.[c];
          if (v == null) return null; const above = spec.level != null ? (v >= spec.level ? " · above today's price" : " · below today's price") : "";
          return `${spec.rowTitle} ${spec.rowTicks[r]} · ${spec.colTitle} ${spec.colTicks[c]} → ${fmt(v)}${above}`; };
      }

      return {
        frame(t, _dt, p, hv) {
          if (born < 0) born = t; const k = Math.min(1, (t - born) / 1.1), e = 1 - Math.pow(1 - k, 3); body.scale.y = Math.max(0.001, e);
          group.rotation.y = p.x * 0.9; group.rotation.x = p.y * 0.2; group.updateMatrixWorld(true);
          const h = pointOn(hv), next = onHit(h); hover = h?.object ?? null; void hover;
          if (next !== shown) { shown = next; setTip(next); }
        },
        recolor(pal) { texts.forEach((t) => paint(t, pal)); recolors.forEach((f) => f(pal)); },
      };
    }, { fov: 36, maxDpr: 1.5 });
  }, [key]);                                // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="p3d">
      <canvas ref={ref} className="p3d-cv" role="img" aria-label={label} />
      {tip && <p className="p3d-tip" aria-hidden="true">{tip}</p>}
    </div>
  );
}
