import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { mountStage, type Palette, type Scene } from "./stage";

type Ser = { label: string; values: (number | null)[] };
export type Plot3DSpec =
  | { kind: "surface"; grid: (number | null)[][]; rowTicks: string[]; colTicks: string[]; rowTitle: string; colTitle: string; valueTitle: string; fmt: (v: number) => string; level?: number; levelName?: string; base?: [number, number] }
  | { kind: "bars"; cats: string[]; series: Ser[]; stack?: boolean; fmt: (v: number) => string; valueTitle?: string }
  | { kind: "ribbon"; x: string[]; series: Ser[]; fmt: (v: number) => string; valueTitle?: string }
  | { kind: "radar"; axes: string[]; series: Ser[] };

const W = 10, H = 3.6;
const root = () => getComputedStyle(document.documentElement);
const serCss = (i: number) => root().getPropertyValue(`--c${(i % 5) + 1}`).trim() || ["#C9A24E", "#2F7A58", "#8A6A25", "#A8392F", "#5A5444"][i % 5];
const colorOf = (s: string, f: string) => { try { return new THREE.Color(s); } catch { return new THREE.Color(f); } };
const serColor = (i: number) => colorOf(serCss(i), "#C9A24E");
const nice = (lo: number, hi: number, n = 4) => Array.from({ length: n + 1 }, (_, k) => lo + ((hi - lo) * k) / n);

/** One labelled 3D plot for every chart kind: value scale on the back and side walls, a label on every axis, hover to read any bar, point or cell.
 *  Everything it draws is also in the flat chart or table it replaces; this only adds depth. */
export default function Plot3D({ spec, label }: { spec: Plot3DSpec; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [tip, setTip] = useState<string | null>(null);
  const fmtRef = useRef<((v: number) => number | string) | null>(null);
  fmtRef.current = "fmt" in spec ? spec.fmt : null;
  const key = JSON.stringify(spec);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    return mountStage(cv, ({ scene, camera, palette, track }): Scene => {
      const fmt = (v: number) => String(fmtRef.current ? fmtRef.current(v) : Math.round(v * 10) / 10);
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
      const pointOn = (p: { x: number; y: number }) => { if (Math.abs(p.x) > 1 || Math.abs(p.y) > 1) return null; v2.set(p.x, -p.y); ray.setFromCamera(v2, camera); return ray.intersectObjects(hot, false)[0] ?? null; };
      let onHit: (h: THREE.Intersection | null) => string | null = () => null;
      let tilt = 0.5;

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
      } else if (spec.kind === "bars") {
        const n = spec.cats.length, rows = spec.stack ? 1 : spec.series.length, zs = Math.min(1.7, 5 / Math.max(1, rows)), D = rows * zs + 0.9, step = W / n, bw = Math.min(0.85, step * 0.62), bd = Math.min(1.1, zs * 0.62);
        const sum = (i: number, sign: number) => spec.series.reduce((a, s) => { const v = s.values[i] ?? 0; return a + (Math.sign(v) === sign ? v : 0); }, 0);
        const hi = Math.max(1e-9, ...(spec.stack ? spec.cats.map((_, i) => sum(i, 1)) : spec.series.flatMap((s) => s.values.map((v) => v ?? 0)))) * 1.08;
        const lo = Math.min(0, ...(spec.stack ? spec.cats.map((_, i) => sum(i, -1)) : spec.series.flatMap((s) => s.values.map((v) => v ?? 0)))) * 1.08;
        const yOf = frame(lo, hi, D, spec.valueTitle), y0 = yOf(0); body.position.y = y0;
        const geo = new THREE.BoxGeometry(1, 1, 1); track(geo);
        const mats = spec.series.map((_, i) => { const m = new THREE.MeshStandardMaterial({ color: serColor(i), metalness: 0.2, roughness: 0.45 }); track(m); recolors.push(() => m.color.copy(serColor(i))); return m; });
        spec.cats.forEach((cat, i) => {
          const x = (i + 0.5) * step - W / 2; let up = 0, dn = 0;
          spec.series.forEach((s, j) => { const v = s.values[i]; if (v == null) return;
            const z = spec.stack ? 0 : (j - (rows - 1) / 2) * zs, a = spec.stack ? (v >= 0 ? up : dn) : 0, b = a + v, h = Math.max(0.02, Math.abs(yOf(b) - yOf(a)));
            const m = new THREE.Mesh(geo, mats[j]); m.scale.set(bw, h, bd); m.position.set(x, (yOf(a) + yOf(b)) / 2 - y0, z); m.userData.tip = `${cat} · ${s.label}: ${fmt(v)}`; body.add(m); hot.push(m);
            if (spec.stack) { if (v >= 0) up = b; else dn = b; } });
          if (n <= 10 || i % Math.ceil(n / 9) === 0 || i === n - 1) label(cat, x, 0, D / 2 + 0.45, { size: 0.36, faint: true });
        });
        if (!spec.stack && rows > 1) spec.series.forEach((s, j) => label(s.label, W / 2 + 0.35, 0, (j - (rows - 1) / 2) * zs, { ax: 0, size: 0.32, bold: true }));
        camera.position.set(0, 6.6, 13.2 + rows * 0.3); camera.lookAt(0, 1.3, 0);
        onHit = (h) => (h ? (h.object.userData.tip as string) ?? null : null);
      } else if (spec.kind === "ribbon") {
        const n = spec.x.length, ix = Array.from({ length: Math.min(n, 90) }, (_, k) => Math.round((k * (n - 1)) / Math.max(1, Math.min(n, 90) - 1)));
        const rows = spec.series.length, zs = Math.min(2, 5 / Math.max(1, rows)), D = rows * zs + 1, dz = zs * 0.66;
        const all = spec.series.flatMap((s) => s.values).filter((v): v is number => v != null);
        let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo || 1) * 0.12; lo = lo >= 0 && lo - pad < 0 ? 0 : lo - pad; hi += pad;
        const yOf = frame(lo, hi, D, spec.valueTitle), y0 = yOf(lo); body.position.y = y0;
        const mk = new THREE.Mesh(new THREE.SphereGeometry(0.14, 16, 12), new THREE.MeshBasicMaterial({ color: palette.ink })); track(mk.geometry); track(mk.material as THREE.Material); mk.visible = false; group.add(mk);
        spec.series.forEach((s, j) => {
          const z = (j - (rows - 1) / 2) * zs; let last: number | null = null;
          const pts = ix.map((src, k) => { const v = s.values[src] ?? last ?? lo; last = v; return new THREE.Vector2((k / Math.max(1, ix.length - 1) - 0.5) * W, yOf(v) - y0); });
          const sh = new THREE.Shape(); sh.moveTo(pts[0].x, 0); pts.forEach((p) => sh.lineTo(p.x, p.y)); sh.lineTo(pts[pts.length - 1].x, 0); sh.closePath();
          const g = new THREE.ExtrudeGeometry(sh, { depth: dz, bevelEnabled: false }); g.translate(0, 0, -dz / 2); track(g);
          const m = new THREE.MeshStandardMaterial({ color: serColor(j), metalness: 0.15, roughness: 0.5, transparent: true, opacity: 0.88 }); track(m); recolors.push(() => m.color.copy(serColor(j)));
          const mesh = new THREE.Mesh(g, m); mesh.position.z = z; mesh.userData = { j, pts, z, dz }; body.add(mesh); hot.push(mesh);
          const lg = new THREE.BufferGeometry().setFromPoints(pts.map((p) => new THREE.Vector3(p.x, p.y, dz / 2 + 0.01))); track(lg);
          const lm = new THREE.LineBasicMaterial({ color: palette.ink }); track(lm); recolors.push((p) => lm.color.copy(p.ink)); const ln = new THREE.Line(lg, lm); ln.position.z = z; body.add(ln);
          if (rows > 1) label(s.label, W / 2 + 0.35, 0, z, { ax: 0, size: 0.32, bold: true });
        });
        const every = Math.ceil(ix.length / 6); ix.forEach((src, k) => { if (k % every === 0 || k === ix.length - 1) label(spec.x[src], (k / Math.max(1, ix.length - 1) - 0.5) * W, 0, D / 2 + 0.45, { size: 0.36, faint: true }); });
        camera.position.set(0, 6.4, 13.4); camera.lookAt(0, 1.3, 0);
        onHit = (h) => { if (!h) { mk.visible = false; return null; } const o = h.object as THREE.Mesh, { j, pts, z, dz: d } = o.userData as { j: number; pts: THREE.Vector2[]; z: number; dz: number };
          const q = o.worldToLocal(h.point.clone()), k = Math.max(0, Math.min(pts.length - 1, Math.round((q.x / W + 0.5) * (pts.length - 1)))), src = ix[k], v = spec.series[j].values[src];
          mk.visible = true; mk.position.set(pts[k].x, pts[k].y + y0, z + d / 2 + 0.05); return v == null ? null : `${spec.x[src]} · ${spec.series[j].label}: ${fmt(v)}`; };
      } else {
        const n = spec.axes.length, R = 3.3, ang = (i: number) => (i / n) * Math.PI * 2 - Math.PI / 2, P = (i: number, v: number) => new THREE.Vector3(Math.cos(ang(i)) * R * v / 100, 0, Math.sin(ang(i)) * R * v / 100);
        const pts: number[] = []; [25, 50, 75, 100].forEach((v) => { for (let i = 0; i < n; i++) { const a = P(i, v), b = P((i + 1) % n, v); pts.push(a.x, 0, a.z, b.x, 0, b.z); } });
        for (let i = 0; i < n; i++) { const e = P(i, 100); pts.push(0, 0, 0, e.x, 0, e.z); label(spec.axes[i], e.x * 1.28, 0, e.z * 1.22, { bold: true, size: 0.36 }); }
        lines(pts, 0.3); [50, 100].forEach((v) => label(String(v), 0.15, 0.06, -R * v / 100 - 0.12, { size: 0.28, faint: true }));
        spec.series.forEach((s, j) => {
          const sh = new THREE.Shape(); s.values.forEach((v, i) => { const p = P(i, v ?? 0); i ? sh.lineTo(p.x, -p.z) : sh.moveTo(p.x, -p.z); }); sh.closePath();
          const g = new THREE.ExtrudeGeometry(sh, { depth: 0.42, bevelEnabled: false }); g.rotateX(-Math.PI / 2); track(g);
          const m = new THREE.MeshStandardMaterial({ color: serColor(j), metalness: 0.1, roughness: 0.5, transparent: true, opacity: 0.5, depthWrite: false }); track(m); recolors.push(() => m.color.copy(serColor(j)));
          body.add(new THREE.Mesh(g, m));
          const lg = new THREE.BufferGeometry().setFromPoints([...s.values.map((v, i) => P(i, v ?? 0).setY(0.43)), P(0, s.values[0] ?? 0).setY(0.43)]); track(lg);
          const lm = new THREE.LineBasicMaterial({ color: serColor(j) }); track(lm); recolors.push(() => lm.color.copy(serColor(j))); body.add(new THREE.Line(lg, lm));
          s.values.forEach((v, i) => { if (v == null) return; const d = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 12), new THREE.MeshStandardMaterial({ color: serColor(j) })); track(d.geometry); track(d.material as THREE.Material);
            d.position.copy(P(i, v)).setY(0.45); d.userData.tip = `${spec.axes[i]} · ${s.label}: ${v}`; body.add(d); hot.push(d); recolors.push(() => (d.material as THREE.MeshStandardMaterial).color.copy(serColor(j))); });
        });
        camera.position.set(0, 7.4, 9.6); camera.lookAt(0, 0, 0); tilt = 0.9;
        onHit = (h) => (h ? (h.object.userData.tip as string) ?? null : null);
      }

      return {
        frame(t, _dt, p) {
          if (born < 0) born = t; const k = Math.min(1, (t - born) / 1.1), e = 1 - Math.pow(1 - k, 3); body.scale.y = Math.max(0.001, e);
          group.rotation.y = p.x * 0.42 * tilt + Math.sin(t * 0.3) * 0.05; group.rotation.x = p.y * 0.05; group.updateMatrixWorld(true);
          const h = pointOn(p), next = onHit(h); hover = h?.object ?? null; void hover;
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
