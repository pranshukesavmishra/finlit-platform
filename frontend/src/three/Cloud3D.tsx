import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { mountStage, type Scene } from "./stage";

export type CloudPoint = { id: string; label: string; x: number; y: number; z: number };
type Props = { points: CloudPoint[]; axes: [string, string, string]; onPick: (id: string) => void; label: string };

/** Companies as points in a box, one axis per chosen column, each scaled to its own range. Move the pointer over a point to read it; click to open
 *  the company. The table below holds the same numbers; this only shows how the companies spread out. */
export default function Cloud3D({ points, axes, onPick, label }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [tip, setTip] = useState<string | null>(null);
  const hit = useRef<string | null>(null);
  const pick = useRef(onPick); pick.current = onPick;
  const key = JSON.stringify([points, axes]);
  useEffect(() => {
    const cv = ref.current; if (!cv || !points.length) return;
    const click = () => { if (hit.current) pick.current(hit.current); };
    cv.addEventListener("click", click);
    const off = mountStage(cv, ({ scene, camera, palette, track }): Scene => {
      const S = 5, rng = (f: (p: CloudPoint) => number): [number, number] => { const v = points.map(f); const a = Math.min(...v), b = Math.max(...v); return [a, b === a ? a + 1 : b]; };
      const rx = rng((p) => p.x), ry = rng((p) => p.y), rz = rng((p) => p.z);
      const norm = (v: number, [a, b]: [number, number]) => ((v - a) / (b - a) - 0.5) * S;
      camera.position.set(0, 4.5, 13.5); camera.lookAt(0, -0.2, 0);
      scene.add(new THREE.AmbientLight(0xffffff, 0.6));
      const sun = new THREE.DirectionalLight(0xfff1d0, 2); sun.position.set(4, 8, 6); scene.add(sun);
      const group = new THREE.Group(); scene.add(group);
      const box = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(S, S, S)), new THREE.LineBasicMaterial({ color: palette.deep, transparent: true, opacity: 0.55 }));
      group.add(box); track(box.geometry); track(box.material as THREE.Material);
      const floor = new THREE.GridHelper(S, 6, palette.deep, palette.deep); floor.position.y = -S / 2; (floor.material as THREE.Material).transparent = true; (floor.material as THREE.Material).opacity = 0.25;
      group.add(floor); track(floor.geometry); track(floor.material as THREE.Material);
      const geo = new THREE.SphereGeometry(0.11, 16, 12), mat = new THREE.MeshStandardMaterial({ color: palette.gold, metalness: 0.6, roughness: 0.3, emissive: palette.gold, emissiveIntensity: 0.25 });
      track(geo); track(mat);
      const inst = new THREE.InstancedMesh(geo, mat, points.length); group.add(inst);
      const m = new THREE.Matrix4(), s = new THREE.Vector3(), q = new THREE.Quaternion(), pos = points.map((p) => new THREE.Vector3(norm(p.x, rx), norm(p.y, ry), norm(p.z, rz)));
      const place = (i: number, k: number) => { s.setScalar(k); m.compose(pos[i], q, s); inst.setMatrixAt(i, m); };
      points.forEach((_, i) => place(i, 1)); inst.instanceMatrix.needsUpdate = true;
      const ray = new THREE.Raycaster(), v2 = new THREE.Vector2(); let cur = -1, born = -1, shown: string | null = null;
      return {
        frame(t, _dt, p) {
          if (born < 0) born = t;
          const k = Math.min(1, (t - born) / 1.0), e = 1 - Math.pow(1 - k, 3);
          group.rotation.y = t * 0.12 + p.x * 0.9; group.rotation.x = p.y * 0.18;
          group.updateMatrixWorld(true);
          let id: number = -1;
          if (Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1) { v2.set(p.x, -p.y); ray.setFromCamera(v2, camera); ray.params.Points = { threshold: 0.2 }; id = ray.intersectObject(inst)[0]?.instanceId ?? -1; }
          if (id !== cur) { if (cur >= 0) place(cur, e); cur = id; }
          points.forEach((_, i) => place(i, i === cur ? 2.2 * e : e)); inst.instanceMatrix.needsUpdate = true;
          const next = cur >= 0 ? points[cur].id : null; hit.current = next;
          if (next !== shown) { shown = next; setTip(cur >= 0 ? points[cur].label : null); }
        },
        recolor(pal) { mat.color.copy(pal.gold); mat.emissive.copy(pal.gold); (box.material as THREE.LineBasicMaterial).color.copy(pal.deep); },
      };
    }, { fov: 34, maxDpr: 1.5 });
    return () => { cv.removeEventListener("click", click); off(); };
  }, [key]);                                // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="cloud3d">
      <canvas ref={ref} className="surface3d" style={{ cursor: tip ? "pointer" : "grab", margin: 0 }} role="img" aria-label={label} />
      <p className="cloud3d-axes" aria-hidden="true">Up: {axes[1]} · Across: {axes[0]} · Depth: {axes[2]}</p>
      {tip && <p className="cloud3d-tip" aria-hidden="true">{tip}</p>}
    </div>
  );
}
