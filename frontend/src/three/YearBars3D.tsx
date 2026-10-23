import { useEffect, useRef } from "react";
import * as THREE from "three";
import { mountStage, type Scene } from "./stage";

/** One column per year, in two layers: money put in (charcoal) and what it has earned on top (gold). The columns grow in left to right and the
 *  whole row can be turned by moving the pointer. The same figures are in the chart and the milestones beside it. */
export default function YearBars3D({ invested, value, label }: { invested: number[]; value: number[]; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const key = invested.join(",") + "|" + value.join(",");
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const n = Math.min(invested.length, value.length); if (!n) return;
    return mountStage(cv, ({ scene, camera, palette, track }): Scene => {
      const top = Math.max(1, ...value), W = 12, H = 4.2, step = W / n, bw = Math.min(0.9, step * 0.72);
      camera.position.set(0, 5.5, 12); camera.lookAt(0, 1.6, 0);
      scene.add(new THREE.AmbientLight(0xffffff, 0.5));
      const sun = new THREE.DirectionalLight(0xfff1d0, 2.3); sun.position.set(4, 9, 7); scene.add(sun);
      const group = new THREE.Group(); scene.add(group);
      const plate = new THREE.Mesh(new THREE.BoxGeometry(W + 1, 0.18, 2.4), new THREE.MeshStandardMaterial({ color: palette.deep, metalness: 0.9, roughness: 0.4 }));
      plate.position.y = -0.09; group.add(plate); track(plate.geometry); track(plate.material as THREE.Material);
      const geo = new THREE.BoxGeometry(bw, 1, bw); track(geo);
      const mInv = new THREE.MeshStandardMaterial({ color: palette.ink, metalness: 0.5, roughness: 0.5 }), mGain = new THREE.MeshStandardMaterial({ color: palette.gold, metalness: 0.55, roughness: 0.35, emissive: palette.gold, emissiveIntensity: 0.25 });
      track(mInv); track(mGain);
      const cols = Array.from({ length: n }, (_, i) => {
        const hi = (Math.min(invested[i], value[i]) / top) * H, hg = (Math.max(0, value[i] - invested[i]) / top) * H, x = (i + 0.5) * step - W / 2;
        const a = new THREE.Mesh(geo, mInv), b = new THREE.Mesh(geo, mGain); a.position.x = b.position.x = x; group.add(a, b);
        return { a, b, hi, hg };
      });
      let born = -1;
      return {
        frame(t, _dt, p) {
          if (born < 0) born = t;
          const k = Math.min(1, (t - born) / 1.6);
          cols.forEach((c, i) => {
            const e = 1 - Math.pow(1 - Math.min(1, Math.max(0, k * 1.5 - (i / n) * 0.5)), 3), hi = Math.max(0.001, c.hi * e), hg = Math.max(0.001, c.hg * e);
            c.a.scale.y = hi; c.a.position.y = hi / 2; c.b.scale.y = hg; c.b.position.y = hi + hg / 2;
          });
          group.rotation.y = -0.35 + p.x * 0.5 + Math.sin(t * 0.3) * 0.08; group.rotation.x = p.y * 0.08;
        },
        recolor(pal) { mInv.color.copy(pal.ink); mGain.color.copy(pal.gold); mGain.emissive.copy(pal.gold); (plate.material as THREE.MeshStandardMaterial).color.copy(pal.deep); },
      };
    }, { fov: 32, maxDpr: 1.5 });
  }, [key]);                                // eslint-disable-line react-hooks/exhaustive-deps
  return <canvas ref={ref} className="surface3d" role="img" aria-label={label} />;
}
