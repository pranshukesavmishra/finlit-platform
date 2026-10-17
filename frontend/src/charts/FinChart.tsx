import { useRef } from "react";
import { css, drawIn, el, vgrad } from "../lib/svg";
import { MINUS, cr, nf, num } from "../lib/format";
import { useChart } from "./useChart";
import type { Series, Table } from "../lib/api";

const get = (t: Table, k: string): Series => t.rows[k] || [];
const v0 = (x: number | null | undefined) => (x == null ? 0 : x);

export type FinKind = "pl" | "bs" | "cf" | "q";

/** Statement charts: P&L (revenue bars, profit bars, margin line), balance-sheet funding stack, cash-flow groups. */
export function FinChart({ kind, pl, bs, cf, ql }: { kind: FinKind; pl: Table; bs: Table; cf: Table; ql: Table }) {
  const tip = useRef<HTMLDivElement>(null);
  const { wrap, svg } = useChart((s, W, first) => {
    const small = W < 560;
    const showTip = (html: (d: HTMLElement) => void, i: number, step: number, x0: number, H: number) => {
      const t = tip.current; if (!t) return;
      const r = s.getBoundingClientRect(); t.hidden = false; t.replaceChildren(); html(t);
      t.style.left = Math.min(Math.max(((x0 + step * (i + 0.5)) / W) * r.width, 90), r.width - 90) + "px"; t.style.top = (H > 0 ? 60 : 60) + "px";
    };
    const hoverBands = (n: number, x0: number, step: number, H: number, render: (i: number, d: HTMLElement) => void) => {
      for (let i = 0; i < n; i++) {
        const r = el("rect", { x: x0 + step * i, y: 0, width: step, height: H, fill: "transparent", rx: 8 }, s);
        r.addEventListener("pointerenter", () => { r.setAttribute("fill", css("--gold-soft")); showTip((d) => render(i, d), i, step, x0, H); });
        r.addEventListener("pointerleave", () => { r.setAttribute("fill", "transparent"); if (tip.current) tip.current.hidden = true; });
      }
    };
    const line = (d: HTMLElement, text: string, cls = "", tag = "span") => { const e = document.createElement(tag); e.className = cls; e.textContent = text; d.appendChild(e); };
    const axisText = (x: number, y: number, t: string, anchor = "middle", fill = css("--faint"), weight = 400) =>
      (el("text", { x, y, fill, "font-size": 11, "text-anchor": anchor, "font-weight": weight, "font-family": "IBM Plex Mono, monospace" }, s).textContent = t);

    if (kind === "pl" || kind === "q") {
      const t = kind === "pl" ? pl : ql, labels = t.periods, n = labels.length;
      const rev = get(t, "revenue").map(v0), np = get(t, "net_profit").map(v0);
      const margins = rev.map((r, i) => (r ? (np[i] / r) * 100 : 0));
      const H = small ? 320 : 360; s.setAttribute("viewBox", `0 0 ${W} ${H}`); s.style.height = H + "px";
      const pl_ = 50, pr = 46, step = (W - pl_ - pr) / n, bw = Math.min(54, step * 0.52), topH = H * 0.44, botT = topH + 40, botH = H - botT - 28;
      const rmx = Math.max(...rev) * 1.1 || 1, nmx = Math.max(...np.map(Math.abs), 1) * 1.15, mmx = Math.max(...margins.map(Math.abs), 1) * 1.2;
      const gRev = vgrad(s, css("--c2"), 0.9, 0.35), gGold = vgrad(s, css("--c1"), 1, 0.55), gNp = vgrad(s, css("--c3"), 0.9, 0.35), gLoss = vgrad(s, css("--loss"), 0.9, 0.4);
      axisText(0, 10, "REVENUE · ₹ L Cr", "start", css("--muted"), 600); axisText(0, botT - 10, "NET PROFIT · ₹ '000 Cr", "start", css("--muted"), 600); axisText(W, botT - 10, "NET MARGIN %", "end", css("--c4"), 600);
      [0, 0.5, 1].forEach((f) => { const yy = 20 + (1 - f) * (topH - 20); el("line", { x1: pl_, x2: W - pr, y1: yy, y2: yy, stroke: css("--border"), "stroke-dasharray": "3 5" }, s); axisText(pl_ - 8, yy + 4, nf((rmx * f) / 1e5, 1), "end"); });
      [0, 0.5, 1].forEach((f) => { const yy = botT + (1 - f) * botH; el("line", { x1: pl_, x2: W - pr, y1: yy, y2: yy, stroke: css("--border"), "stroke-dasharray": "3 5" }, s); axisText(pl_ - 8, yy + 4, nf((nmx * f) / 1000, 0), "end"); });
      [0, 0.5, 1].forEach((f) => axisText(W - pr + 8, botT + (1 - f) * botH + 4, nf(mmx * f, 1), "start", css("--faint")));
      let ml = "";
      labels.forEach((lab, i) => {
        const cx = pl_ + step * (i + 0.5), last = i === n - 1, rh = (rev[i] / rmx) * (topH - 20);
        el("rect", { x: cx - bw / 2, y: topH - rh, width: bw, height: Math.max(0, rh), rx: 6, fill: last ? gGold : gRev }, s);
        if (!small || last) axisText(cx, topH - rh - 7, nf(rev[i] / 1e5, 2), "middle", last ? css("--gold") : css("--muted"), 600);
        const nh = (Math.abs(np[i]) / nmx) * botH;
        el("rect", { x: cx - bw / 2, y: botT + botH - nh, width: bw, height: Math.max(0, nh), rx: 6, fill: np[i] < 0 ? gLoss : last ? gGold : gNp }, s);
        ml += `${i ? "L" : "M"}${cx},${botT + (1 - Math.max(0, margins[i]) / mmx) * botH}`;
        axisText(cx, H - 6, lab.replace(/^(\w{3}) 20(\d\d)$/, "$1 $2"), "middle", last ? css("--gold") : css("--faint"), last ? 700 : 400);
      });
      drawIn(el("path", { d: ml, fill: "none", stroke: css("--c4"), "stroke-width": 2.4, "stroke-linejoin": "round" }, s), first);
      labels.forEach((_, i) => el("circle", { cx: pl_ + step * (i + 0.5), cy: botT + (1 - Math.max(0, margins[i]) / mmx) * botH, r: 4.5, fill: css("--c4"), stroke: css("--s1"), "stroke-width": 2 }, s));
      hoverBands(n, pl_, step, H, (i, d) => { line(d, labels[i], "faint"); line(d, `Revenue ₹${cr(rev[i])} Cr`, "", "b"); line(d, `Net profit ₹${num(np[i], 0)} Cr · margin ${nf(margins[i], 1)}%`, "muted"); });
    } else if (kind === "bs") {
      const labels = bs.periods, n = labels.length, H = 320; s.setAttribute("viewBox", `0 0 ${W} ${H}`); s.style.height = H + "px";
      const pl_ = 50, pr = 16, pt = 22, pb = 28, step = (W - pl_ - pr) / n, bw = Math.min(64, step * 0.56);
      const eq = get(bs, "total_equity").map(v0), bo = get(bs, "borrowings").map(v0), ta = get(bs, "total_assets").map(v0);
      const oth = ta.map((a, i) => Math.max(0, a - eq[i] - bo[i])), mx = Math.max(...ta) * 1.1 || 1;
      const parts: [string, number[], string][] = [["Equity + reserves", eq, "--c1"], ["Borrowings", bo, "--c2"], ["Other liabilities", oth, "--c4"]];
      const fills = parts.map(([, , c]) => vgrad(s, css(c), 0.95, 0.6));
      [0, 0.5, 1].forEach((f) => { const yy = pt + (1 - f) * (H - pt - pb); el("line", { x1: pl_, x2: W - pr, y1: yy, y2: yy, stroke: css("--border"), "stroke-dasharray": "3 5" }, s); axisText(pl_ - 8, yy + 4, nf((mx * f) / 1e5, 1) + "L", "end"); });
      labels.forEach((lab, i) => {
        const cx = pl_ + step * (i + 0.5); let base = H - pb;
        parts.forEach(([, arr], k) => { const h = (arr[i] / mx) * (H - pt - pb); el("rect", { x: cx - bw / 2, y: base - h, width: bw, height: Math.max(0, h - 2), rx: k === 2 ? 6 : 3, fill: fills[k] }, s); base -= h; });
        axisText(cx, base - 8, nf(ta[i] / 1e5, 2) + "L", "middle", i === n - 1 ? css("--gold") : css("--muted"), 600); axisText(cx, H - 6, lab, "middle");
      });
      hoverBands(n, pl_, step, H, (i, d) => { line(d, `${labels[i]} · funded by`, "faint"); line(d, `₹${cr(ta[i])} Cr`, "", "b"); parts.forEach(([nm, arr]) => line(d, `${nm} ₹${cr(arr[i])} Cr`, "muted", "div")); });
    } else {
      const labels = cf.periods, n = labels.length, H = 320; s.setAttribute("viewBox", `0 0 ${W} ${H}`); s.style.height = H + "px";
      const pl_ = 50, pr = 16, pt = 22, pb = 28, step = (W - pl_ - pr) / n, bw = Math.min(24, step * 0.2);
      const op = get(cf, "operating").map(v0), inv = get(cf, "investing").map(v0), fin = get(cf, "financing").map(v0), fcf = get(cf, "free_cash_flow").map(v0);
      const all = [...op, ...inv, ...fin, ...fcf], mx = Math.max(...all, 1) * 1.1, mn = Math.min(...all, 0) * 1.1;
      const y = (v: number) => pt + ((mx - v) / (mx - mn)) * (H - pt - pb);
      [mn, 0, mx].forEach((v) => { el("line", { x1: pl_, x2: W - pr, y1: y(v), y2: y(v), stroke: css("--border"), "stroke-dasharray": v === 0 ? "" : "3 5" }, s); axisText(pl_ - 8, y(v) + 4, (v < 0 ? MINUS : "") + nf(Math.abs(v) / 1000, 0) + "k", "end"); });
      const keys: [string, number[], string][] = [["Operating", op, "--c3"], ["Investing", inv, "--c2"], ["Financing", fin, "--c4"]];
      let fl = "";
      labels.forEach((lab, i) => {
        const cx = pl_ + step * (i + 0.5);
        keys.forEach(([, arr, c], j) => { const v = arr[i], x0 = cx + (j - 1) * (bw + 5) - bw / 2; el("rect", { x: x0, y: Math.min(y(v), y(0)), width: bw, height: Math.abs(y(v) - y(0)), rx: 4, fill: css(c), opacity: v >= 0 ? 1 : 0.7 }, s); });
        fl += `${i ? "L" : "M"}${cx},${y(fcf[i])}`; axisText(cx, H - 6, lab, "middle", i === n - 1 ? css("--gold") : css("--faint"), i === n - 1 ? 700 : 400);
      });
      drawIn(el("path", { d: fl, fill: "none", stroke: css("--c1"), "stroke-width": 2.4 }, s), first);
      labels.forEach((_, i) => { const cx = pl_ + step * (i + 0.5), cy = y(fcf[i]); el("path", { d: `M${cx},${cy - 6}L${cx + 6},${cy}L${cx},${cy + 6}L${cx - 6},${cy}Z`, fill: css("--c1"), stroke: css("--s1"), "stroke-width": 1.5 }, s); });
      hoverBands(n, pl_, step, H, (i, d) => { line(d, labels[i], "faint"); line(d, `Free cash flow ₹${num(fcf[i], 0)} Cr`, "", "b"); keys.forEach(([nm, arr]) => line(d, `${nm} ₹${num(arr[i], 0)} Cr`, "muted", "div")); });
    }
  }, [kind, pl, bs, cf, ql]);
  return <div className="chart" ref={wrap}><svg ref={svg} role="img" aria-label="Financial statement chart" /><div className="tip" ref={tip} hidden /></div>;
}
