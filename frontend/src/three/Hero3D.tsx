import { useEffect, useRef } from "react";
import * as THREE from "three";
import { mountStage, type Palette, type Scene } from "./stage";

/** Home hero backdrop: a slowly moving gold price landscape with candlesticks rising from it and a rupee coin turning above, all drawn in the
 *  site's own colours. Sits behind the text, takes no clicks, and is only loaded for devices that can run it (see support.ts). */
const COLS = 110, ROWS = 56, W = 70, D = 40;

function coinFace(p: Palette): THREE.CanvasTexture {
  const c = document.createElement("canvas"); c.width = c.height = 512; const g = c.getContext("2d")!;
  const gold = "#" + p.gold.getHexString(), deep = "#" + p.deep.getHexString();
  const grad = g.createRadialGradient(200, 180, 30, 256, 256, 280); grad.addColorStop(0, "#F3DD9B"); grad.addColorStop(0.55, gold); grad.addColorStop(1, deep);
  g.fillStyle = grad; g.fillRect(0, 0, 512, 512);
  g.strokeStyle = deep; g.lineWidth = 10; g.beginPath(); g.arc(256, 256, 226, 0, Math.PI * 2); g.stroke();
  g.lineWidth = 3; g.beginPath(); g.arc(256, 256, 206, 0, Math.PI * 2); g.stroke();
  // the rupee sign is drawn as strokes, so it does not depend on a font that has the glyph
  g.strokeStyle = deep; g.lineWidth = 34; g.lineJoin = "miter"; g.lineCap = "butt"; g.beginPath();
  g.moveTo(160, 150); g.lineTo(360, 150); g.moveTo(160, 226); g.lineTo(360, 226);
  g.moveTo(190, 150); g.lineTo(250, 150); g.arc(250, 218, 68, -Math.PI / 2, Math.PI / 2); g.lineTo(190, 286); g.lineTo(335, 410); g.stroke();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}

const hill = (x: number, z: number, t: number) =>
  Math.sin(x * 0.19 + t * 0.35) * 1.5 + Math.sin(x * 0.07 - t * 0.2 + z * 0.1) * 2.6 + Math.sin(z * 0.28 + x * 0.12 + t * 0.5) * 0.75;

export default function Hero3D() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    return mountStage(cv, ({ scene, camera, palette, track }): Scene => {
      scene.fog = new THREE.Fog(palette.paper, 26, 44);
      camera.position.set(0, 9, 20); camera.lookAt(0, 0.5, -3);
      scene.add(new THREE.AmbientLight(0xffffff, 0.35));
      const key = new THREE.DirectionalLight(0xfff1d0, 2.2); key.position.set(6, 12, 8); scene.add(key);

      // landscape: a solid body (hides the lines behind the hills) and the gold grid drawn over it
      const geo = new THREE.PlaneGeometry(W, D, COLS, ROWS); geo.rotateX(-Math.PI / 2); track(geo);
      const pos = geo.attributes.position as THREE.BufferAttribute, base = Float32Array.from(pos.array as Float32Array);
      const body = new THREE.MeshBasicMaterial({ color: palette.paper, transparent: true, opacity: 0.9, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
      const grid = new THREE.MeshBasicMaterial({ color: palette.gold, wireframe: true, transparent: true, opacity: palette.light ? 0.6 : 0.45 });
      const land = new THREE.Group(); land.add(new THREE.Mesh(geo, body), new THREE.Mesh(geo, grid)); land.position.set(0, -3.6, 0); scene.add(land);

      // candlesticks standing on the landscape
      const cand = new THREE.Group(); land.add(cand);
      const stick = new THREE.BoxGeometry(0.42, 1, 0.42), wick = new THREE.BoxGeometry(0.05, 1, 0.05); track(stick); track(wick);
      const up = new THREE.MeshStandardMaterial({ color: palette.gain, roughness: 0.5, metalness: 0.1, envMapIntensity: 0.25 }), down = new THREE.MeshStandardMaterial({ color: palette.loss, roughness: 0.5, metalness: 0.1, envMapIntensity: 0.25 });
      const wickMat = new THREE.MeshBasicMaterial({ color: palette.ink }); track(up); track(down); track(wickMat);
      const cs = Array.from({ length: 16 }, (_, i) => {
        const gain = Math.sin(i * 12.9898) > -0.2, x = 3 + i * 1.6 + Math.sin(i * 3.1) * 0.6, z = -2 + Math.sin(i * 1.7) * 9;
        const body = new THREE.Mesh(stick, gain ? up : down), w = new THREE.Mesh(wick, wickMat); cand.add(body, w);
        return { x, z, body, w, h: 0.9 + ((i * 37) % 10) / 5, ph: i * 0.9 };
      });

      // the coin
      const face = coinFace(palette); track(face);
      const rim = new THREE.MeshStandardMaterial({ color: palette.gold, metalness: 1, roughness: 0.22 });
      const cap = new THREE.MeshStandardMaterial({ map: face, metalness: 0.85, roughness: 0.3 });
      const R = 1.4, T = 0.26;
      // a rim (open cylinder along Z) with a flat face on each side, so the rupee reads the right way round from the front and the back
      const rimGeo = new THREE.CylinderGeometry(R, R, T, 96, 1, true), faceGeo = new THREE.CircleGeometry(R * 0.995, 96); track(rimGeo); track(faceGeo);
      const coin = new THREE.Group(); const rimMesh = new THREE.Mesh(rimGeo, rim); rimMesh.rotation.x = Math.PI / 2;
      const front = new THREE.Mesh(faceGeo, cap); front.position.z = T / 2; const back = new THREE.Mesh(faceGeo, cap); back.position.z = -T / 2; back.rotation.y = Math.PI;
      coin.add(rimMesh, front, back); track(rim); track(cap);
      const spin = new THREE.Group(); spin.add(coin); spin.position.set(13.3, 5.5, -2); scene.add(spin);

      return {
        frame(t) {
          for (let i = 0; i < pos.count; i++) pos.setY(i, hill(base[i * 3], base[i * 3 + 2], t) * (0.55 + 0.45 * (1 - (base[i * 3 + 2] + D / 2) / D)));
          pos.needsUpdate = true;
          for (const c of cs) {
            const y = hill(c.x, c.z, t) * (0.55 + 0.45 * (1 - (c.z + D / 2) / D)), h = c.h * (0.85 + 0.15 * Math.sin(t * 0.9 + c.ph));
            c.body.scale.y = h; c.body.position.set(c.x, y + h / 2, c.z); c.w.scale.y = h * 1.7; c.w.position.set(c.x, y + h * 0.85, c.z);
          }
          spin.rotation.y = t * 0.55; spin.position.y = 5.5 + Math.sin(t * 0.8) * 0.35;
          camera.position.y = 9; camera.lookAt(0, 0.5, -3);
        },
        recolor(pal) {
          (scene.fog as THREE.Fog).color.copy(pal.paper);
          body.color.copy(pal.paper); grid.color.copy(pal.gold); grid.opacity = pal.light ? 0.6 : 0.45; rim.color.copy(pal.gold);
          wickMat.color.copy(pal.ink);
        },
      };
    }, { fov: 42 });
  }, []);
  return <canvas ref={ref} className="hero3d" aria-hidden="true" />;
}
