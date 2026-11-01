// Twelve simple line illustrations for the page header (in-house, monochrome). They draw with currentColor; the one accent stroke uses the theme's gold.
// Decorative only: the svg is aria-hidden. Styles: styles/page-header.css (class prefix ph-).
import type { ReactNode } from "react";

export type PhArtKind = "screener" | "chart" | "calculator" | "calendar" | "portfolio" | "funds" | "news" | "macro" | "compare" | "report" | "rating" | "search";
export const PH_ART_KINDS: PhArtKind[] = ["screener", "chart", "calculator", "calendar", "portfolio", "funds", "news", "macro", "compare", "report", "rating", "search"];

const Win = () => (<g><rect x="12" y="14" width="196" height="122" rx="12" /><path d="M12 36h196" /><circle cx="26" cy="25" r="2.4" /><circle cx="36" cy="25" r="2.4" /><circle cx="46" cy="25" r="2.4" /></g>);
const A = ({ children }: { children: ReactNode }) => <g className="ph-acc">{children}</g>;

const ART: Record<PhArtKind, () => ReactNode> = {
  screener: () => (<><Win />
    {[0, 1, 2, 3].map((i) => (<g key={i}><path d={`M28 ${54 + i * 19}h${[70, 52, 84, 40][i]}`} /><path d={`M${108 + (i % 2) * 14} ${54 + i * 19}h${[26, 44, 18, 30][i]}`} opacity=".55" /></g>))}
    <A><circle cx="168" cy="96" r="20" /><path d="m183 111 14 14" /><path d="M160 96h16M168 88v16" opacity=".6" /></A></>),
  chart: () => (<><Win />
    <path d="M28 120V50M28 120h164" /><path d="M28 98h164M28 76h164" opacity=".25" />
    <path d="M28 108l24-14 22 8 26-30 24 12 28-34 24 18" /><A><path d="M28 112l24-8 22 4 26-18 24 6 28-22 24 8" /><circle cx="152" cy="62" r="4" /></A></>),
  calculator: () => (<>
    <rect x="62" y="10" width="96" height="130" rx="12" /><rect x="74" y="22" width="72" height="26" rx="6" /><path d="M84 38h28" opacity=".6" />
    {[0, 1, 2].map((r) => [0, 1, 2].map((c) => <rect key={r + "" + c} x={76 + c * 24} y={60 + r * 24} width="18" height="16" rx="4" opacity={c === 2 ? 1 : 0.7} />))}
    <A><rect x="124" y="108" width="18" height="16" rx="4" /><path d="M129 114h8M129 118h8" /></A></>),
  calendar: () => (<>
    <rect x="20" y="16" width="180" height="120" rx="12" /><path d="M20 44h180M60 8v16M160 8v16" />
    {[0, 1, 2, 3, 4, 5, 6].map((c) => [0, 1, 2].map((r) => <circle key={c + "" + r} cx={42 + c * 23} cy={64 + r * 24} r="2.2" opacity=".6" />))}
    <A><rect x="107" y="84" width="22" height="20" rx="6" /></A></>),
  portfolio: () => (<><Win />
    <circle cx="80" cy="88" r="30" /><circle cx="80" cy="88" r="16" opacity=".4" /><A><path d="M80 58a30 30 0 0 1 28 38" /><path d="M80 72a16 16 0 0 1 14 20" /></A>
    <path d="M132 64h56M132 82h40M132 100h50M132 118h30" opacity=".6" /><circle cx="124" cy="64" r="2" /><circle cx="124" cy="82" r="2" /><circle cx="124" cy="100" r="2" /><circle cx="124" cy="118" r="2" /></>),
  funds: () => (<><Win />
    {[0, 1, 2, 3, 4].map((i) => <rect key={i} x={30 + i * 22} y={118 - [22, 34, 28, 48, 60][i]} width="14" height={[22, 34, 28, 48, 60][i]} rx="3" opacity={i === 4 ? 1 : 0.7} />)}
    <path d="M30 76l22-10 22 8 22-18 22 6" opacity=".55" /><A><circle cx="168" cy="82" r="20" /><path d="M168 72v20M161 78h14M161 86h14" /></A></>),
  news: () => (<>
    <rect x="24" y="16" width="156" height="120" rx="10" /><path d="M180 44h18a6 6 0 0 1 6 6v68a18 18 0 0 1-18 18" />
    <path d="M40 36h72" strokeWidth="3" /><rect x="40" y="52" width="48" height="36" rx="5" />
    <path d="M98 56h66M98 70h66M98 84h44M40 104h124M40 118h96" opacity=".6" /><A><path d="M40 36h40" /></A></>),
  macro: () => (<><Win />
    <circle cx="80" cy="88" r="34" /><ellipse cx="80" cy="88" rx="14" ry="34" opacity=".5" /><path d="M46 88h68M52 70h56M52 106h56" opacity=".5" />
    <path d="M136 112l16-12 14 6 22-26" /><A><path d="M180 80h8v8" /><path d="M136 124h52" opacity=".6" /></A></>),
  compare: () => (<><Win />
    <rect x="26" y="48" width="70" height="76" rx="8" /><rect x="124" y="48" width="70" height="76" rx="8" />
    {[0, 1, 2].map((i) => (<g key={i}><path d={`M36 ${66 + i * 20}h${[44, 30, 38][i]}`} opacity=".7" /><path d={`M134 ${66 + i * 20}h${[32, 48, 24][i]}`} opacity=".7" /></g>))}
    <A><path d="M104 80h12M112 74l6 6-6 6M112 98h-12M104 92l-6 6 6 6" /></A></>),
  report: () => (<>
    <path d="M52 12h86l30 30v94a6 6 0 0 1-6 6H52a6 6 0 0 1-6-6V18a6 6 0 0 1 6-6z" /><path d="M138 12v30h30" />
    <path d="M62 56h50M62 70h76" opacity=".6" /><path d="M64 118V98M80 118v-24M96 118v-14M112 118V88" /><path d="M62 118h64" opacity=".5" />
    <A><circle cx="146" cy="108" r="16" /><path d="m139 108 5 5 9-10" /></A></>),
  rating: () => (<><Win />
    <path d="M44 112a46 46 0 0 1 92 0" /><path d="M44 112a46 46 0 0 1 14-33" opacity=".5" /><A><path d="M90 112l22-30" /><circle cx="90" cy="112" r="4" /></A>
    {[0, 1, 2, 3].map((i) => <rect key={i} x="150" y={56 + i * 16} width={[38, 28, 34, 20][i]} height="8" rx="4" opacity=".7" />)}</>),
  search: () => (<><Win />
    <path d="M28 54h64M28 70h46M28 86h58M28 102h40M28 118h52" opacity=".55" />
    <A><circle cx="146" cy="88" r="26" /><path d="m165 107 20 20" /><path d="M134 88h24" opacity=".6" /></A></>),
};

export function PageArt({ kind }: { kind: PhArtKind }) {
  return (
    <svg className="ph-art" viewBox="0 0 220 150" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" data-art={kind}>
      {ART[kind]()}
    </svg>);
}
