import { useEffect, useRef } from "react";
import * as THREE from "three";
import { mountStage, type Scene } from "./stage";

export type SurfaceProps = {
  grid: (number | null)[][];            // grid[row][col]; null cells are holes that sit at the floor
  base?: [number, number];              // row and column of the base case
  level?: number;                       // a flat sheet at this value (for example today's price)
  label: string;                        // plain-words description for screen readers
};

/** A value surface you can look at from any side: the grid becomes a gold landscape, with a glass sheet at the reference level and a marker on
 *  the base case. The same numbers are in the table beside it; this only adds the third dimension. */
export default function Surface3D({ grid, base, level, label }: SurfaceProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const key = JSON.stringify([grid, base, level]);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    return mountStage(cv, ({ scene, camera, palette, track }): Scene => {
      const R = grid.length, C = grid[0]?.length ?? 0;
      const vals = grid.flat().filter((v): v is number => v != null && isFinite(v));
      const lo = Math.min(0, ...vals, level ?? 0), hi = Math.max(1e-9, ...vals, level ?? 0), span = hi - lo || 1;
      const H = 3.2, W = 7, D = 7;
      const hOf = (v: number | null) => (v == null ? 0 : ((v - lo) / span) * H);
      camera.position.set(0, 7.5, 12.5); camera.lookAt(0, 1.2, 0);
      scene.add(new THREE.AmbientLight(0xffffff, 0.5));
      const sun = new THREE.DirectionalLight(0xfff1d0, 2.2); sun.position.set(5, 10, 6); scene.add(sun);
      const group = new THREE.Group(); scene.add(group);

      const geo = new THREE.PlaneGeometry(W, D, Math.max(1, C - 1), Math.max(1, R - 1)); geo.rotateX(-Math.PI / 2); track(geo);
      const pos = geo.attributes.position, col = new Float32Array(pos.count * 3);
      const paint = (pal: typeof palette) => {
        for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) {
          const i = r * C + c, v = grid[r][c];
          const t = v == null ? 0 : (v - lo) / span;
          const k = level != null && v != null && v < level ? pal.loss : pal.gold;
          const colr = new THREE.Color().copy(pal.deep).lerp(k, 0.35 + 0.65 * t);
          col[i * 3] = colr.r; col[i * 3 + 1] = colr.g; col[i * 3 + 2] = colr.b;
        }
        geo.setAttribute("color", new THREE.BufferAttribute(col, 3)); geo.attributes.color.needsUpdate = true;
      };
      for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) pos.setY(r * C + c, hOf(grid[r][c]));
      geo.computeVertexNormals(); paint(palette);
      const mat = new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0.7, roughness: 0.38, side: THREE.DoubleSide, flatShading: true }); track(mat);
      const mesh = new THREE.Mesh(geo, mat); group.add(mesh);
      const wire = new THREE.LineSegments(new THREE.WireframeGeometry(geo), new THREE.LineBasicMaterial({ color: palette.ink, transparent: true, opacity: 0.22 }));
      group.add(wire); track(wire.geometry); track(wire.material as THREE.Material);

      const floor = new THREE.GridHelper(W + 1.5, 8, palette.deep, palette.deep); floor.position.y = -0.02;
      (floor.material as THREE.Material).transparent = true; (floor.material as THREE.Material).opacity = 0.25; group.add(floor); track(floor.geometry); track(floor.material as THREE.Material);

      let sheet: THREE.Mesh | null = null;
      if (level != null && isFinite(level)) {
        sheet = new THREE.Mesh(new THREE.PlaneGeometry(W + 0.6, D + 0.6), new THREE.MeshBasicMaterial({ color: palette.ink, transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false }));
        sheet.rotation.x = -Math.PI / 2; sheet.position.y = hOf(level); group.add(sheet); track(sheet.geometry); track(sheet.material as THREE.Material);
      }
      let pin: THREE.Mesh | null = null;
      if (base && grid[base[0]]?.[base[1]] != null) {
        const x = (base[1] / Math.max(1, C - 1) - 0.5) * W, z = (base[0] / Math.max(1, R - 1) - 0.5) * D, y = hOf(grid[base[0]][base[1]]);
        pin = new THREE.Mesh(new THREE.SphereGeometry(0.2, 24, 16), new THREE.MeshStandardMaterial({ color: palette.ink, emissive: palette.gold, emissiveIntensity: 0.6, metalness: 0.4, roughness: 0.3 }));
        pin.position.set(x, y + 0.25, z); group.add(pin); track(pin.geometry); track(pin.material as THREE.Material);
      }
      let born = -1;
      return {
        frame(t, _dt, p) {
          if (born < 0) born = t;
          const k = Math.min(1, (t - born) / 1.2), e = 1 - Math.pow(1 - k, 3);      // the surface grows up once
          mesh.scale.y = e; wire.scale.y = e; if (pin) pin.position.y = (hOf(grid[base![0]][base![1]]) + 0.25) * e;
          group.rotation.y = -0.5 + Math.sin(t * 0.25) * 0.25 + p.x * 0.7; group.rotation.x = p.y * 0.1;
        },
        recolor(pal) {
          paint(pal); (wire.material as THREE.LineBasicMaterial).color.copy(pal.ink);
          if (sheet) (sheet.material as THREE.MeshBasicMaterial).color.copy(pal.ink);
          if (pin) { const m = pin.material as THREE.MeshStandardMaterial; m.color.copy(pal.ink); m.emissive.copy(pal.gold); }
        },
      };
    }, { fov: 34, maxDpr: 1.5 });
  }, [key]);                                // eslint-disable-line react-hooks/exhaustive-deps
  return <canvas ref={ref} className="surface3d" role="img" aria-label={label} />;
}
