import { useEffect, useRef, useState } from "react";
import { useThemeKey } from "../lib/ui";

/** Measures the container, then calls `draw(svg, width)` whenever data, width or theme change.
 *  Charts read CSS variables at draw time, so a theme switch simply redraws. */
export function useChart(draw: (svg: SVGSVGElement, width: number, first: boolean) => void, deps: unknown[]) {
  const wrap = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [w, setW] = useState(0);
  const drawn = useRef(false);
  const theme = useThemeKey();

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => {
      const nw = Math.round(e.contentRect.width);
      setW((old) => (Math.abs(old - nw) > 1 ? nw : old));
    });
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!svg.current || w < 40) return;
    svg.current.innerHTML = "";
    const first = !drawn.current;
    drawn.current = true;
    draw(svg.current, w, first);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w, theme, ...deps]);

  return { wrap, svg };
}
