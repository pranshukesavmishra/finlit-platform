// Small shared pieces of the Prism charts: a width observer, the "Show as table" link and the table that every chart can open.
// The charts themselves live in ./pzr (History, Parts). Every chart states its conclusion in its aria-label and offers a table.
import { useEffect, useRef, useState } from "react";

export function useWidth<T extends HTMLElement>(initial = 640): [(el: T | null) => void, number] {
  const [w, setW] = useState(initial);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = (el: T | null) => {
    ro.current?.disconnect();
    if (!el) return;
    setW(Math.max(240, Math.round(el.getBoundingClientRect().width) || initial));
    if (typeof ResizeObserver === "undefined") return;
    ro.current = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    ro.current.observe(el);
  };
  useEffect(() => () => ro.current?.disconnect(), []);
  return [ref, w];
}

export function ShowTable({ on, set }: { on: boolean; set: (b: boolean) => void }) {
  return <button type="button" className="pzr-link pzr-noprint" aria-expanded={on} onClick={() => set(!on)}>{on ? "Hide table" : "Show as table"}</button>;
}
export function ChartTable({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="pzr-ctable"><table><caption>{caption}</caption><thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => (j === 0 ? <th scope="row" key={j}>{c}</th> : <td key={j}>{c}</td>))}</tr>)}</tbody></table></div>
  );
}
