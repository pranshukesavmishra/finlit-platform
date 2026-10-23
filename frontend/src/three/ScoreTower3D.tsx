import { useEffect, useRef } from "react";
import * as THREE from "three";
import { mountStage, type Scene } from "./stage";

/** The five score pillars as a small gold-and-charcoal tower you can see from above and the side, turning slowly. The numbers are also in the
 *  list next to it; this only adds the third dimension. */
export default function ScoreTower3D({ scores }: { scores: number[] }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const key = scores.join(",");
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    return mountStage(cv, ({ scene, camera, palette, track }): Scene => {
      camera.position.set(0, 6.5, 11); camera.lookAt(0, 1.6, 0);
      scene.add(new THREE.AmbientLight(0xffffff, 0.45));
      const sun = new THREE.DirectionalLight(0xfff1d0, 2.4); sun.position.set(5, 9, 6); scene.add(sun);
      const group = new THREE.Group(); scene.add(group);
      const plate = new THREE.Mesh(new THREE.CylinderGeometry(5.2, 5.4, 0.35, 64), new THREE.MeshStandardMaterial({ color: palette.deep, metalness: 0.9, roughness: 0.35 }));
      plate.position.y = -0.18; group.add(plate); track(plate.geometry); track(plate.material as THREE.Material);
      const mats = [palette.gold, palette.ink, palette.gold, palette.ink, palette.gold].map((c, i) => new THREE.MeshStandardMaterial({ color: c, metalness: i % 2 ? 0.5 : 0.95, roughness: i % 2 ? 0.5 : 0.25 }));
      const geo = new THREE.BoxGeometry(1.4, 1, 1.4); track(geo); mats.forEach((m) => track(m));
      const bars = scores.slice(0, 5).map((s, i) => {
        const a = (i / 5) * Math.PI * 2 - Math.PI / 2, m = new THREE.Mesh(geo, mats[i]); m.position.set(Math.cos(a) * 3, 0, Math.sin(a) * 3); group.add(m);
        return { m, h: Math.max(0.15, (s / 100) * 6) };
      });
      let born = -1;
      return {
        frame(t, _dt, p) {
          if (born < 0) born = t;
          const k = Math.min(1, (t - born) / 1.4), e = 1 - Math.pow(1 - k, 3);    // the pillars rise once when the card appears
          bars.forEach((b, i) => { const h = Math.max(0.01, b.h * Math.min(1, Math.max(0, e * 1.4 - i * 0.08))); b.m.scale.y = h; b.m.position.y = h / 2; });
          group.rotation.y = t * 0.3 + p.x * 0.6; group.rotation.x = p.y * 0.08;
        },
        recolor(pal) { mats.forEach((m, i) => m.color.copy(i % 2 ? pal.ink : pal.gold)); (plate.material as THREE.MeshStandardMaterial).color.copy(pal.deep); },
      };
    }, { fov: 32, maxDpr: 1.5 });
  }, [key]);
  return <canvas ref={ref} className="tower3d" role="img" aria-label={`Five score pillars as a 3D tower: ${scores.join(", ")} out of 100`} />;
}
