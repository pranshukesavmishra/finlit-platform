/** The blog hero's drawing: three stacked books (Myths, Explainers, Hot Topics), a bulb and a small bar chart, in the site's cream and one gold. Decorative: hidden from screen readers. */
export function BlogArt() {
  return (
    <svg className="bl-art" viewBox="0 0 420 300" role="presentation" aria-hidden="true">
      <g stroke="var(--gold)" strokeWidth="1.4" strokeLinecap="round" opacity=".55">
        {[[330, 36, 330, 18], [356, 48, 370, 36], [304, 46, 294, 30], [370, 76, 388, 72]].map(([a, b, c, d], i) => <path key={i} d={`M${a} ${b}L${c} ${d}`} />)}
      </g>
      <g transform="translate(318 62)"><path d="M0 22a22 22 0 1 1 28 0c-6 5-6 9-6 14h-16c0-5 0-9-6-14z" fill="var(--s1)" stroke="var(--gold)" strokeWidth="2" /><path d="M7 42h14M9 48h10" stroke="var(--gold)" strokeWidth="2" strokeLinecap="round" /><path d="M10 22l4 6 4-6" fill="none" stroke="var(--gold)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></g>
      <g transform="translate(34 196)" fill="var(--gold)">{[22, 40, 58, 78].map((h, i) => <rect key={i} x={i * 20} y={-h} width="13" height={h} rx="2" opacity={0.45 + i * 0.15} />)}<path d="M-6 -88l24 20 22-12 24 14" fill="none" stroke="var(--gold)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></g>
      {[
        { y: 196, w: 250, x: 126, label: "Hot Topics", fill: "var(--s2)" },
        { y: 146, w: 232, x: 140, label: "Explainers", fill: "var(--s1)" },
        { y: 96, w: 214, x: 150, label: "Myths", fill: "var(--s2)" },
      ].map((b) => (
        <g key={b.label}>
          <rect x={b.x} y={b.y} width={b.w} height="42" rx="5" fill={b.fill} stroke="var(--gold)" strokeWidth="1.6" />
          <rect x={b.x + 10} y={b.y + 6} width={b.w - 24} height="30" rx="3" fill="none" stroke="var(--border-strong, var(--border))" strokeWidth="1" />
          <text x={b.x + b.w / 2 - 6} y={b.y + 26} textAnchor="middle" fontSize="14" fontWeight="700" fontFamily="var(--sans)" fill="var(--text)" letterSpacing=".06em">{b.label.toUpperCase()}</text>
        </g>
      ))}
      <path d="M110 244h296" stroke="var(--gold)" strokeWidth="2" strokeLinecap="round" opacity=".6" />
    </svg>
  );
}
