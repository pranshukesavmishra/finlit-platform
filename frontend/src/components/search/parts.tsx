// Small pieces of the search results: logo tile, flag, score ring, price and change, highlighted text, sparkline, 52-week bar.
import { useState } from "react";
import { apiUrl } from "../../lib/api";
import { DEMO } from "../../lib/demo";
import { MINUS, dateIN, initials, nf } from "../../lib/format";
import { BAND_LABEL, highlight, type Band, type Kind } from "../../lib/globalSearch";

const TINTS = ["#2A4E8A", "#7A5B16", "#2E6B57", "#7B3F5E", "#4B4A8C", "#8A4B2A", "#3E5F73", "#6B5A2E"];
const tint = (s: string) => TINTS[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % TINTS.length];
/** Logo files: from our own API (or the saved copies in the demo build). */
const logoSrc = (path: string) => (DEMO ? `${import.meta.env.BASE_URL}demo/logos/${path.split("/").pop()}` : apiUrl(path));

/** The company's own logo on a light tile (readable on both themes); initials in a coloured tile when there is none or it fails to load. */
export function Logo({ src, name, kind, size = 40 }: { src?: string | null; name: string; kind: Kind; size?: number }) {
  const [broken, setBroken] = useState(false);
  const style = { width: size, height: size, borderRadius: Math.round(size * 0.28) };
  if (kind === "news") return <span className="gs-logo gs-logo-news" style={style} aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 4h11v16H6a2 2 0 0 1-2-2V5a1 1 0 0 1 1-1Zm11 5h3a1 1 0 0 1 1 1v8a2 2 0 0 1-4 0M8 8h5M8 12h5M8 16h3" /></svg></span>;
  if (src && !broken) {
    return <span className="gs-logo gs-logo-img" style={style}><img src={logoSrc(src)} alt="" loading="lazy" decoding="async" width={size} height={size} onError={() => setBroken(true)} referrerPolicy="no-referrer" /></span>;
  }
  return <span className="gs-logo gs-logo-txt" style={{ ...style, background: `linear-gradient(140deg, ${tint(name)}, color-mix(in srgb, ${tint(name)} 55%, #000))`, fontSize: Math.round(size * 0.34) }} aria-hidden="true">{initials(name.replace(/^the\s+/i, ""))}</span>;
}

/** India's flag, drawn (emoji flags do not show on Windows). */
export function FlagIN() {
  return (
    <svg className="gs-flag" viewBox="0 0 18 12" role="img" aria-label="India">
      <rect width="18" height="4" fill="#FF9933" /><rect y="4" width="18" height="4" fill="#FFFFFF" /><rect y="8" width="18" height="4" fill="#138808" />
      <circle cx="9" cy="6" r="1.45" fill="none" stroke="#000080" strokeWidth=".5" /><circle cx="9" cy="6" r=".35" fill="#000080" />
    </svg>
  );
}

const RING: Record<string, string> = { strong: "var(--gain)", healthy: "var(--k1)", mixed: "var(--warn)", watch: "var(--loss)" };
/** The 0-100 score as a ring with its band word. "locked" (below Silver) shows a lock; unscored shows a dash. Never buy/sell words. */
export function ScoreRing({ score, band, size = 38, word = true }: { score?: number | null; band?: Band; size?: number; word?: boolean }) {
  if (band === "locked") {
    return (
      <span className="gs-score gs-lock" title="Scores are part of the Silver plan">
        <span className="gs-ring" style={{ width: size, height: size }}><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5.5" y="10.5" width="13" height="9" rx="2" /><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" /></svg></span>
        {word && <span className="gs-band">Silver</span>}
      </span>
    );
  }
  if (score == null) return <span className="gs-score gs-none" title="Not scored yet"><span className="gs-ring" style={{ width: size, height: size }}>{MINUS}</span>{word && <span className="gs-band">Not scored</span>}</span>;
  const key = band && RING[band] ? band : score >= 78 ? "strong" : score >= 62 ? "healthy" : score >= 45 ? "mixed" : "watch";
  const r = 15, c = 2 * Math.PI * r, color = RING[key];
  return (
    <span className="gs-score" style={{ "--rc": color } as React.CSSProperties} title={`Score ${score} of 100 · ${BAND_LABEL[key]}`}>
      <span className="gs-ring" style={{ width: size, height: size }}>
        <svg viewBox="0 0 36 36" aria-hidden="true"><circle cx="18" cy="18" r={r} className="gs-ring-bg" /><circle cx="18" cy="18" r={r} className="gs-ring-fg" strokeDasharray={`${(c * score) / 100} ${c}`} /></svg>
        <b>{score}</b>
      </span>
      {word && <span className="gs-band">{BAND_LABEL[key]}</span>}
    </span>
  );
}

/** ₹ price and the day's change. A price from an earlier day is labelled with its date and shown without the up/down colour. */
export function PriceChange({ price, chg, date, today, unit = "₹" }: { price?: number | null; chg?: number | null; date?: string | null; today: string; unit?: string }) {
  if (price == null) return <span className="gs-px gs-px-none">Price on open</span>;
  const old = !!date && date !== today;
  const dir = chg == null || Math.abs(chg) < 0.005 ? "flat" : chg > 0 ? "up" : "down";
  return (
    <span className={`gs-px ${old ? "old" : dir}`}>
      <b>{unit}{nf(price, 2)}</b>
      {chg != null && <span className="gs-chg"><i aria-hidden="true">{dir === "up" ? "▲" : dir === "down" ? "▼" : "•"}</i>{chg < 0 ? MINUS : chg > 0 ? "+" : ""}{nf(chg, 2)}%</span>}
      {old && date && <small>close {dateIN(date, { day: "numeric", month: "short" })}</small>}
    </span>
  );
}

export function Hl({ text, q }: { text: string; q: string }) {
  return <>{highlight(text, q).map((p, i) => (p.hit ? <mark key={i}>{p.t}</mark> : <span key={i}>{p.t}</span>))}</>;
}

/** A small closing-price line for the preview card. */
export function Spark({ values, up }: { values: number[]; up: boolean }) {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length < 2) return null;
  const lo = Math.min(...v), hi = Math.max(...v), w = 300, h = 72, pad = 4;
  const pts = v.map((x, i) => [(i / (v.length - 1)) * w, h - pad - ((x - lo) / (hi - lo || 1)) * (h - 2 * pad)]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join("");
  return (
    <svg className={`gs-spark ${up ? "up" : "down"}`} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id="gsFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="currentColor" stopOpacity=".28" /><stop offset="1" stopColor="currentColor" stopOpacity="0" /></linearGradient></defs>
      <path d={`${line}L${w} ${h}L0 ${h}Z`} fill="url(#gsFill)" /><path d={line} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Where today's price sits between the 52-week low and high. */
export function Range52({ low, high, price }: { low: number | null; high: number | null; price: number | null }) {
  if (low == null || high == null || price == null || high <= low) return null;
  const at = Math.max(0, Math.min(100, ((price - low) / (high - low)) * 100));
  return (
    <div className="gs-r52">
      <div className="gs-r52-bar"><i style={{ left: `${at}%` }} /></div>
      <div className="gs-r52-k"><span>52W low ₹{nf(low, 0)}</span><span>52W high ₹{nf(high, 0)}</span></div>
    </div>
  );
}
