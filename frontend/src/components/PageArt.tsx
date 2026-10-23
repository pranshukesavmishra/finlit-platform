/** Large illustrated panels for page headers, and generated blog covers. Decorative SVG, animated with CSS, themed by variables. */
const Defs = ({ k }: { k: string }) => (
  <defs>
    <linearGradient id={`pg${k}`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--gold-2)" /><stop offset="1" stopColor="var(--gold-deep)" /></linearGradient>
    <linearGradient id={`pf${k}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--gold)" stopOpacity=".4" /><stop offset="1" stopColor="var(--gold)" stopOpacity="0" /></linearGradient>
    <radialGradient id={`pr${k}`} cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="var(--gold)" stopOpacity=".28" /><stop offset="1" stopColor="var(--gold)" stopOpacity="0" /></radialGradient>
  </defs>
);
const Rings = ({ k }: { k: string }) => (<g><circle cx="240" cy="170" r="165" fill={`url(#pr${k})`} />{[150, 112, 76].map((r, i) => <circle key={r} cx="240" cy="170" r={r} fill="none" stroke="var(--gold)" strokeDasharray={i === 1 ? "2 7" : "none"} opacity={0.5 - i * 0.12} />)}</g>);
const chip = (x: number, y: number, t: string, c: string, d = 0) => (
  <g className="pa-float" style={{ animationDelay: `${d}ms` }} transform={`translate(${x} ${y})`}>
    <rect x="1" y="3" width={t.length * 6.8 + 34} height="30" rx="15" fill="#000" opacity=".22" />
    <rect width={t.length * 6.8 + 34} height="30" rx="15" fill="#fff" /><circle cx="15" cy="15" r="5" fill={c} /><text x="28" y="19.5" fontSize="12" fontWeight="600" fill="#14130F" fontFamily="IBM Plex Sans, sans-serif">{t}</text>
  </g>
);

const scenes: Record<string, (k: string) => React.ReactNode> = {
  services: (k) => (<>
    <Rings k={k} />
    {[0, 1, 2, 3, 4].map((i) => <g key={i} className="pa-rise" style={{ animationDelay: `${i * 110}ms` }}><rect x={92 + i * 54} y={250 - i * 34} width="44" height={i * 34 + 24} rx="9" fill={`url(#pg${k})`} opacity={0.35 + i * 0.16} /><rect x={92 + i * 54} y={250 - i * 34} width="44" height="6" rx="3" fill="#fff" opacity=".5" /></g>)}
    <path className="pa-draw" d="M70 232 150 200 220 170 290 120 372 66" fill="none" stroke="var(--c3)" strokeWidth="3" strokeLinecap="round" strokeDasharray="6 7" />
    <g transform="translate(372 66)"><circle r="16" fill="var(--c3)" opacity=".25" className="pa-pulse" /><path d="M-6 8V-10l14 5-14 5" fill="var(--c3)" stroke="var(--c3)" strokeWidth="2" strokeLinejoin="round" /></g>
    {chip(40, 40, "First session", "var(--gold)")}{chip(30, 288, "5 services", "var(--c2)", 600)}
  </>),
  about: (k) => (<>
    <Rings k={k} />
    <g transform="translate(240 150)">
      <path d="M-112 -34 0 -92 112 -34z" fill={`url(#pg${k})`} opacity=".9" /><rect x="-118" y="-30" width="236" height="10" rx="3" fill={`url(#pg${k})`} opacity=".6" />
      {[-84, -28, 28, 84].map((x, i) => <g key={x} className="pa-rise" style={{ animationDelay: `${i * 120}ms` }}><rect x={x - 14} y="-14" width="28" height="104" rx="6" fill="var(--s2)" stroke="var(--gold)" strokeOpacity=".6" /><path d={`M${x - 6} -6V82M${x + 6} -6V82`} stroke="var(--gold)" strokeOpacity=".25" /></g>)}
      <rect x="-124" y="94" width="248" height="12" rx="4" fill={`url(#pg${k})`} opacity=".7" />
    </g>
    {chip(34, 56, "Research", "var(--c3)")}{chip(300, 40, "Reasoning you can follow", "var(--gold)", 500)}{chip(60, 280, "Discipline over noise", "var(--c4)", 900)}
  </>),
  why: (k) => (<>
    <defs><linearGradient id={`fn${k}`} x1="0" x2="1"><stop offset="0" stopColor="var(--c2)" /><stop offset="1" stopColor="var(--gold)" /></linearGradient></defs>
    <Rings k={k} />
    {[[60, 330, 0, "144 cr"], [92, 270, 1, "39 cr"], [124, 214, 2, "12.5 cr"], [156, 160, 3, "38.5 cr"]].map(([y, w, i, t]) => <g key={t as string} className="pa-rise" style={{ animationDelay: `${(i as number) * 130}ms` }}><rect x={240 - (w as number) / 2} y={(y as number) - 20 + 20} width={w as number} height="26" rx="13" fill={`url(#fn${k})`} opacity={0.32 + (i as number) * 0.18} /><text x="240" y={(y as number) + 38} textAnchor="middle" fontSize="12" fontWeight="600" fill="var(--text)" fontFamily="IBM Plex Mono, monospace">{t as string}</text></g>)}
    <path d="M240 232V268" stroke="var(--gold)" strokeWidth="2" strokeDasharray="3 4" /><circle cx="240" cy="276" r="10" fill="var(--gold)" className="pa-pulse" />
    {chip(30, 44, "India's population", "var(--c2)")}{chip(310, 296, "Addressable", "var(--gold)", 700)}
  </>),
  contact: (k) => (<>
    <Rings k={k} />
    <g transform="translate(150 120)"><rect width="190" height="110" rx="18" fill="var(--s2)" stroke="var(--border-strong)" /><path d="M0 18 95 70 190 18" fill="none" stroke={`url(#pg${k})`} strokeWidth="3" strokeLinejoin="round" /><path d="M26 92h70M26 78h110" stroke="var(--border-strong)" strokeWidth="5" strokeLinecap="round" /></g>
    <g transform="translate(130 250)" className="pa-float"><path d="M0 0 120-50 26 30-6 8z" fill="var(--gold)" /><path d="M-6 8 120-50 40 20z" fill="var(--gold-deep)" opacity=".7" /></g>
    <path className="pa-draw" d="M40 290C100 300 130 270 140 250" fill="none" stroke="var(--gold)" strokeWidth="2" strokeDasharray="4 6" />
    {chip(300, 72, "We reply within a day", "var(--c3)")}{chip(36, 70, "Hello", "var(--c2)", 500)}
  </>),
  portfolio: (k) => (<>
    <Rings k={k} />
    {[[70, 190, 40, 1], [104, 170, 54, 1], [138, 188, 36, 0], [172, 150, 60, 1], [206, 128, 46, 1], [240, 140, 40, 0], [274, 104, 58, 1], [308, 86, 48, 1], [342, 72, 40, 1]].map(([x, y, h, up], i) => <g key={i} className="pa-rise" style={{ animationDelay: `${i * 70}ms` }}><path d={`M${x} ${(y as number) - 14}V${(y as number) + (h as number) + 14}`} stroke={up ? "var(--gain)" : "var(--loss)"} strokeWidth="2" /><rect x={(x as number) - 8} y={y as number} width="16" height={h as number} rx="3" fill={up ? "var(--gain)" : "var(--loss)"} opacity=".8" /></g>)}
    <path d="M50 250 120 224 190 200 260 166 330 118 410 58V310H50z" fill={`url(#pf${k})`} /><path className="pa-draw" d="M50 250 120 224 190 200 260 166 330 118 410 58" fill="none" stroke="var(--gold)" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
    {chip(40, 40, "Net ROI 18.5%", "var(--gain)")}{chip(300, 288, "455 trades", "var(--c2)", 600)}
  </>),
  blog: (k) => (<>
    <Rings k={k} />
    {[[-14, 120, 0.5], [0, 140, 0.75], [14, 160, 1]].map(([r, y, o], i) => <g key={i} transform={`translate(${150 + i * 34} ${(y as number) - 60}) rotate(${r})`} opacity={o as number}><rect width="170" height="212" rx="16" fill="var(--s2)" stroke="var(--border-strong)" />{i === 2 && <><rect x="18" y="20" width="90" height="10" rx="5" fill={`url(#pg${k})`} /><path d="M18 52h134M18 70h120M18 88h100" stroke="var(--border-strong)" strokeWidth="6" strokeLinecap="round" /><path d="M18 180 52 140 86 156 122 112 152 124" fill="none" stroke="var(--gold)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><path className="pa-draw" d="M18 180 52 140 86 156 122 112 152 124" fill="none" stroke="var(--c2)" strokeWidth="1.5" /></>}</g>)}
    {chip(40, 40, "Articles", "var(--gold)")}{chip(310, 280, "Reports · Data", "var(--c4)", 700)}
  </>),
  research: (k) => (<>
    <Rings k={k} />
    <g transform="translate(240 170)">
      {[["--p-quality", 56, 104], ["--p-growth", 44, 91], ["--p-profit", 51, 78], ["--p-balance", 75, 65], ["--p-tech", 31, 52]].map(([c, v, r], i) => { const R = r as number, C = 2 * Math.PI * R, len = ((v as number) / 100) * C * 0.75;
        return <g key={c as string} transform="rotate(135)"><circle r={R} fill="none" stroke="var(--s3)" strokeWidth="7" strokeLinecap="round" strokeDasharray={`${C * 0.75} ${C}`} />
          <circle r={R} fill="none" stroke={`var(${c})`} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${len} ${C}`} style={{ animationDelay: `${i * 140}ms` }} /></g>; })}
      <text y="8" textAnchor="middle" fontSize="38" fontFamily="Newsreader Variable, Newsreader, Georgia, serif" fontWeight="300" fill="var(--text)">51</text>
      <text y="28" textAnchor="middle" fontSize="8" letterSpacing="1.6" fill="var(--faint)" fontFamily="IBM Plex Sans, sans-serif">FINLIT SCORE</text>
    </g>
    {chip(30, 60, "5,700+ stocks", "var(--c3)")}{chip(300, 40, "Updated daily", "var(--gold)", 500)}{chip(318, 292, "5 pillars", "var(--c1)", 900)}
  </>),
};

export function PageArt({ kind }: { kind: keyof typeof scenes }) {
  return <div className="pa" aria-hidden="true"><svg viewBox="0 0 480 340" role="presentation"><Defs k={kind} />{scenes[kind](kind)}</svg></div>;
}

/** Generated cover for posts without an image: deterministic from the title so each looks distinct. */
export function CoverArt({ seed, type }: { seed: string; type: string }) {
  let h = 7; for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) | 0;
  const r = (n: number) => { h = (h * 1103515245 + 12345) & 0x7fffffff; return (h % 1000) / 1000 * n; };
  const accent = { ARTICLE: "var(--gold)", PDF: "var(--c2)", SPREADSHEET: "var(--c3)", IMAGE: "var(--c4)" }[type] || "var(--gold)";
  const pts = Array.from({ length: 9 }, (_, i) => [i * 40, 150 - r(70) - i * 6] as const);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join("");
  const id = "cv" + Math.abs(h);
  return (
    <svg className="cover-art" viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" aria-hidden="true" style={{ "--ac": accent } as React.CSSProperties}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={accent} stopOpacity=".5" /><stop offset="1" stopColor={accent} stopOpacity="0" /></linearGradient></defs>
      {[0, 1, 2].map((i) => <circle key={i} cx={r(320)} cy={r(120)} r={40 + r(60)} fill={accent} opacity=".07" />)}
      {Array.from({ length: 14 }, (_, i) => <rect key={i} x={12 + i * 22} y={180 - 10 - r(60)} width="10" height="70" rx="3" fill={accent} opacity=".10" />)}
      <path d={`${d}V180H0z`} fill={`url(#${id})`} /><path d={d} fill="none" stroke={accent} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {pts.filter((_, i) => i % 3 === 2).map(([x, y]) => <circle key={x} cx={x} cy={y} r="5" fill="var(--s1)" stroke={accent} strokeWidth="2.5" />)}
    </svg>
  );
}
