import { useEffect, useRef } from "react";

/** Animated market backdrop: layered glowing price waves, drifting candles and a particle mesh that reacts to the pointer.
 *  Pauses when off-screen or hidden, and draws one still frame for visitors who prefer reduced motion. */
export function HeroCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const ctx = cv.getContext("2d"); if (!ctx) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, raf = 0, visible = true, t0 = performance.now();
    const mouse = { x: -999, y: -999 };
    const css = (n: string, f: string) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || f;
    let gold = "#e7c56b", blue = "#86a5dc", violet = "#c9daf5";
    const small = () => matchMedia("(max-width: 760px)").matches;
    type P = { x: number; y: number; vx: number; vy: number };
    let pts: P[] = [];
    const resize = () => {
      const r = cv.getBoundingClientRect(); const dpr = Math.min(devicePixelRatio || 1, 2);
      w = r.width; h = r.height; cv.width = w * dpr; cv.height = h * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = small() ? 26 : 58;
      pts = Array.from({ length: n }, () => ({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .25, vy: (Math.random() - .5) * .25 }));
      gold = css("--gold", gold); blue = css("--c2", blue); violet = css("--c3", violet);
    };
    const wave = (x: number, t: number, k: number) =>
      Math.sin(x * .006 + t * .0004 * k) * 34 + Math.sin(x * .0135 + t * .0007 * k + k) * 16 + Math.sin(x * .0031 - t * .0002) * 52;
    const draw = (now: number) => {
      const t = now - t0; ctx.clearRect(0, 0, w, h);
      // three glowing price lines
      const lines: [string, number, number, number][] = [[gold, .9, .8, 1], [blue, .5, .86, 1.6], [violet, .4, .92, 2.2]];
      for (const [col, a, yy, k] of lines) {
        const base = h * yy; ctx.beginPath();
        for (let x = 0; x <= w; x += 6) { const y = base + wave(x, t, k) - (x / w) * h * .16; x ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
        ctx.lineWidth = k === 1 ? 2.2 : 1.4; ctx.strokeStyle = col; ctx.globalAlpha = a; ctx.shadowColor = col; ctx.shadowBlur = 18; ctx.stroke();
        ctx.shadowBlur = 0; ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
        const g = ctx.createLinearGradient(0, base - 80, 0, h); g.addColorStop(0, col); g.addColorStop(1, "transparent");
        ctx.globalAlpha = a * .13; ctx.fillStyle = g; ctx.fill();
      }
      // candles riding the gold line
      ctx.globalAlpha = .5; const step = small() ? 34 : 26;
      for (let x = step; x < w; x += step) {
        const y = h * .8 + wave(x, t, 1) - (x / w) * h * .16, j = Math.sin(x * 12.9898) * 43758.5453, r = j - Math.floor(j);
        const body = 10 + r * 26, up = r > .42, col = up ? css("--gain", "#34d399") : css("--loss", "#f87171");
        ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, y - body - 10); ctx.lineTo(x, y + body + 10); ctx.stroke();
        ctx.globalAlpha = .38; ctx.fillRect(x - 3.5, y - body / 2, 7, body); ctx.globalAlpha = .5;
      }
      // particle mesh
      ctx.globalAlpha = 1;
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy; if (p.x < 0 || p.x > w) p.vx *= -1; if (p.y < 0 || p.y > h) p.vy *= -1;
        const dx = p.x - mouse.x, dy = p.y - mouse.y, d = Math.hypot(dx, dy);
        if (d < 140) { p.x += (dx / d) * 1.4; p.y += (dy / d) * 1.4; }
      }
      for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
        const d = Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y);
        if (d < 120) { ctx.strokeStyle = gold; ctx.globalAlpha = (1 - d / 120) * .22; ctx.lineWidth = .8; ctx.beginPath(); ctx.moveTo(pts[i].x, pts[i].y); ctx.lineTo(pts[j].x, pts[j].y); ctx.stroke(); }
      }
      ctx.fillStyle = gold; for (const p of pts) { ctx.globalAlpha = .55; ctx.beginPath(); ctx.arc(p.x, p.y, 1.6, 0, 6.3); ctx.fill(); }
      ctx.globalAlpha = 1;
    };
    const loop = (now: number) => { if (visible && !document.hidden) draw(now); raf = requestAnimationFrame(loop); };
    resize();
    const ro = new ResizeObserver(() => { resize(); if (reduce) draw(t0 + 4000); }); ro.observe(cv);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }); io.observe(cv);
    const mv = (e: PointerEvent) => { const r = cv.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top; };
    const lv = () => { mouse.x = mouse.y = -999; };
    const host = cv.parentElement!; host.addEventListener("pointermove", mv); host.addEventListener("pointerleave", lv);
    const th = new MutationObserver(() => { gold = css("--gold", gold); blue = css("--c2", blue); violet = css("--c3", violet); });
    th.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    if (reduce) draw(t0 + 4000); else raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); th.disconnect(); host.removeEventListener("pointermove", mv); host.removeEventListener("pointerleave", lv); };
  }, []);
  return <canvas ref={ref} className="hero-canvas" aria-hidden="true" />;
}
