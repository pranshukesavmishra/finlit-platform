// The FinLit logo, as vector shapes traced from the brand artwork (scripts/trace-logo.py), and its loading animation.
//  <FinLitLogo/>   the logo as a still picture (the website header)
//  <LogoLoader/>   the same logo building itself: the staircase draws, F and n appear, the person walks onto the first step and climbs to his place in
//                  the "i", then L, i and t appear, the bars rise and the growth arrow sweeps up (about 2.7 s of a 3.4 s loop)
// Pure CSS on inline SVG (public/logo-loader.css, loaded by index.html, so the same logo also shows before any script has run). Colours follow the theme
// (navy or white letters, gold, green). Reduced motion: the finished logo, still. The loader markup is checked against the splash in index.html by a test.
import { LOGO_ARROW, LOGO_BAR1, LOGO_BAR2, LOGO_BAR3, LOGO_F, LOGO_HAIR, LOGO_HEAD, LOGO_IDOT, LOGO_ISTEM, LOGO_N, LOGO_PERSON, LOGO_STAIRSL_GOLD, LOGO_STAIRL_WHITE, LOGO_T, LOGO_VIEWBOX } from "./logoPaths";

export function LogoMark({ play = false, className = "" }: { play?: boolean; className?: string }) {
  return (
    <svg className={("ll " + (play ? "ll-play " : "") + className).trim()} viewBox={LOGO_VIEWBOX} aria-hidden="true" focusable="false">
      <defs><linearGradient id="ll-grad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#3F8D75" /><stop offset="1" stopColor="#276253" /></linearGradient></defs>
      <g className="ll-all">
        <g className="ll-stairs"><path className="ll-gold" d={LOGO_STAIRSL_GOLD} /><path className="ll-ink" d={LOGO_STAIRL_WHITE} /></g>
        <path className="ll-ink ll-F" d={LOGO_F} />
        <path className="ll-ink ll-n" d={LOGO_N} />
        <g className="ll-i"><circle className="ll-gold" cx={LOGO_IDOT.cx} cy={LOGO_IDOT.cy} r={LOGO_IDOT.r} /><path className="ll-gold" d={LOGO_ISTEM} /></g>
        <path className="ll-gold ll-t" d={LOGO_T} />
        <path className="ll-gold ll-hair" d={LOGO_HAIR} />
        <path className="ll-grad ll-b1" d={LOGO_BAR1} />
        <path className="ll-grad ll-b2" d={LOGO_BAR2} />
        <path className="ll-grad ll-b3" d={LOGO_BAR3} />
        <path className="ll-grad ll-arrow" d={LOGO_ARROW} />
        <g className="ll-person"><circle className="ll-gold" cx={LOGO_HEAD.cx} cy={LOGO_HEAD.cy} r={LOGO_HEAD.r} /><path className="ll-ink" d={LOGO_PERSON} /></g>
      </g>
    </svg>
  );
}

/** The logo as a still picture, for the header and other places that show the brand. */
export function FinLitLogo({ className = "" }: { className?: string }) {
  return <LogoMark className={className} />;
}

type Size = "sm" | "md" | "lg" | "xl";

/** The logo building itself, with a line for screen readers. `size`: sm (beside a line of text), md, lg (a section), xl (the splash). */
export function LogoLoader({ size = "md", label = "Loading", className = "" }: { size?: Size; label?: string; className?: string }) {
  return (
    <span className={("ll-stack " + className).trim()} role="status" aria-live="polite">
      <LogoMark play className={"ll-" + size} />
      <span className="ll-sr">{label}</span>
    </span>
  );
}

/** A whole page or section that is still loading: the logo, centred. */
export function PageLoading({ label = "Loading", size = "lg" }: { label?: string; size?: Size }) {
  return <div className="ll-full"><LogoLoader size={size} label={label} /></div>;
}

/** Beside a line of text, for a small wait ("Calculating…"). */
export function InlineLoading({ children }: { children: React.ReactNode }) {
  return <span className="ll-inline"><LogoLoader size="sm" label="Loading" />{children}</span>;
}
