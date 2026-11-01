import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type CSSProperties } from "react";

const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const SAFETY_MS = 1200;

/**
 * Fades content in once as it scrolls into view.
 * Content is visible by default: the hidden starting state (`rv-pre`) is only added after mount, and only for blocks that start
 * below the fold, so a failed observer, a nested scroll container, reduced motion, printing or a slow device can never leave a block
 * invisible. It never changes layout (opacity and transform only). A block that is on screen is always revealed within SAFETY_MS.
 */
export function Reveal({ children, delay = 0, className = "", as: Tag = "div" }: { children: ReactNode; delay?: number; className?: string; as?: "div" | "section" | "li" }) {
  const ref = useRef<HTMLElement>(null);
  const [state, setState] = useState<"idle" | "pre" | "in">("idle");
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || reduced()) return;
    // on screen, or already scrolled past, or not laid out (display:none): all mean "do not keep it hidden"
    const onScreen = () => { const b = el.getBoundingClientRect(); return b.top < (window.innerHeight || document.documentElement.clientHeight) * 0.97 || (b.width === 0 && b.height === 0); };
    if (onScreen()) return; // already in view: never hide it, no flash
    setState("pre");
    let done = false;
    const show = () => { if (done) return; done = true; cleanup(); setState("in"); };
    const io = typeof IntersectionObserver !== "undefined" ? new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) show(); }, { rootMargin: "0px 0px -4% 0px", threshold: 0 }) : null;
    io?.observe(el);
    // belt and braces: scroll (any container, capture), resize and a slow tick re-check the position, and the safety timer
    // reveals anything that is on screen but whose observer never fired.
    const check = () => { if (onScreen()) show(); };
    window.addEventListener("scroll", check, { passive: true, capture: true });
    window.addEventListener("resize", check);
    const tick = window.setInterval(check, SAFETY_MS);
    const safety = window.setTimeout(check, SAFETY_MS);
    const cleanup = () => { io?.disconnect(); window.removeEventListener("scroll", check, true); window.removeEventListener("resize", check); clearInterval(tick); clearTimeout(safety); };
    return () => { done = true; cleanup(); };
  }, []);
  const style = { "--d": `${delay}ms` } as CSSProperties;
  return <Tag ref={ref as never} className={`rv ${state === "pre" ? "rv-pre" : state === "in" ? "in" : ""} ${className}`} style={style}>{children}</Tag>;
}

/** Counts up to a number when it first appears. */
export function CountUp({ to, decimals = 0, prefix = "", suffix = "", duration = 1200 }: { to: number; decimals?: number; prefix?: string; suffix?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [v, setV] = useState(0);
  useEffect(() => {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setV(to); return; }
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const step = (now: number) => {
        const k = Math.min(1, (now - t0) / duration);
        setV(to * (1 - Math.pow(1 - k, 4)));
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, [to, duration]);
  return <span ref={ref}>{prefix}{v.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</span>;
}
