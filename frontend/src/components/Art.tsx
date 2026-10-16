/** Small illustrated scenes for the service cards. Pure SVG, theme-aware through CSS variables, decorative only. */
const defs = (id: string) => (
  <defs>
    <linearGradient id={`g${id}`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--ac)" /><stop offset="1" stopColor="color-mix(in srgb, var(--ac) 30%, transparent)" /></linearGradient>
    <linearGradient id={`f${id}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--ac)" stopOpacity=".45" /><stop offset="1" stopColor="var(--ac)" stopOpacity="0" /></linearGradient>
  </defs>
);
const Frame = ({ id, children }: { id: string; children: React.ReactNode }) => (
  <svg className="art" viewBox="0 0 320 150" role="presentation" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
    {defs(id)}
    <g opacity=".5" stroke="var(--border-strong)" strokeWidth="1">{[30, 60, 90, 120].map((y) => <path key={y} d={`M0 ${y}H320`} strokeDasharray="2 6" />)}</g>
    {children}
  </svg>
);

const scenes: Record<string, React.ReactNode> = {
  // 0 → 1: seedling growing out of ascending bars
  seed: (<Frame id="a">
    {[0, 1, 2, 3, 4, 5].map((i) => <rect key={i} className="grow" style={{ animationDelay: `${i * 90}ms` }} x={40 + i * 40} y={120 - 14 - i * 12} width="24" height={14 + i * 12} rx="5" fill="url(#ga)" />)}
    <path d="M250 70c0-18 8-30 22-36-2 16-8 28-22 36z" fill="var(--gain)" opacity=".9" /><path d="M250 70c0-14-7-24-20-28 1 13 7 22 20 28z" fill="var(--gain)" opacity=".6" /><path d="M250 120V70" stroke="var(--gain)" strokeWidth="3" strokeLinecap="round" />
  </Frame>),
  // wealth: rising area line with milestone dots
  wealth: (<Frame id="b">
    <path d="M10 124 60 108 105 112 150 84 195 90 245 52 310 26V150H10z" fill="url(#fb)" />
    <path className="draw" d="M10 124 60 108 105 112 150 84 195 90 245 52 310 26" fill="none" stroke="var(--ac)" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
    {[[60, 108], [150, 84], [245, 52]].map(([x, y]) => <g key={x}><circle cx={x} cy={y} r="9" fill="var(--ac)" opacity=".22" /><circle cx={x} cy={y} r="4.5" fill="var(--s1)" stroke="var(--ac)" strokeWidth="2.5" /></g>)}
  </Frame>),
  // family: linked circles
  family: (<Frame id="c">
    <path d="M90 90 160 52 230 90M160 52V104" stroke="var(--ac)" strokeWidth="2" opacity=".5" strokeDasharray="4 5" />
    {[[160, 52, 22], [90, 90, 17], [230, 90, 17], [160, 108, 13]].map(([x, y, r], i) => <g key={i}><circle cx={x} cy={y} r={r + 8} fill="var(--ac)" opacity=".13" className="pulse" style={{ animationDelay: `${i * 300}ms` }} /><circle cx={x} cy={y} r={r} fill="url(#gc)" /><circle cx={x} cy={y - r * .25} r={r * .34} fill="#fff" opacity=".85" /><path d={`M${x - r * .62} ${y + r * .7}a${r * .62} ${r * .5} 0 0 1 ${r * 1.24} 0`} fill="#fff" opacity=".85" /></g>)}
  </Frame>),
  // global: globe with orbit
  globe: (<Frame id="d">
    <g transform="translate(160 75)">
      <circle r="46" fill="url(#gd)" opacity=".35" /><circle r="46" fill="none" stroke="var(--ac)" strokeWidth="2" />
      <ellipse rx="20" ry="46" fill="none" stroke="var(--ac)" strokeWidth="1.5" opacity=".7" /><path d="M-46 0H46M-40 -22H40M-40 22H40" stroke="var(--ac)" strokeWidth="1.5" opacity=".6" />
      <g className="orbit"><ellipse rx="86" ry="22" fill="none" stroke="var(--ac)" strokeWidth="1.5" strokeDasharray="3 5" opacity=".7" /><circle cx="86" cy="0" r="6" fill="var(--ac)" /></g>
    </g>
  </Frame>),
  // review: donut + magnifier
  review: (<Frame id="e">
    <g transform="translate(130 76)">
      {[[0, .42, "var(--c1)"], [.42, .72, "var(--c2)"], [.72, .9, "var(--c3)"], [.9, 1, "var(--c4)"]].map(([a, b, c], i) => { const r = 40, C = 2 * Math.PI * r; return <circle key={i} r={r} fill="none" stroke={c as string} strokeWidth="16" strokeDasharray={`${((b as number) - (a as number)) * C - 3} ${C}`} strokeDashoffset={-(a as number) * C} transform="rotate(-90)" />; })}
    </g>
    <g transform="translate(212 92)"><circle r="26" fill="var(--s1)" fillOpacity=".7" stroke="var(--ac)" strokeWidth="5" /><path d="m19 19 22 22" stroke="var(--ac)" strokeWidth="7" strokeLinecap="round" /><path d="m-10 4 7 7 14-16" fill="none" stroke="var(--gain)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /></g>
  </Frame>),
};
export const SERVICE_ART = ["seed", "wealth", "family", "globe", "review"];
export function ServiceArt({ kind }: { kind: string }) { return <div className="art-wrap">{scenes[kind]}</div>; }
