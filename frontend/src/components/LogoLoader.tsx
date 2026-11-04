// The FinLit logo loader: the person of the logo climbs the gold staircase, the bars rise, the arrow draws (about 0.9 s, looping while something loads).
// Pure CSS on an inline SVG; the styles are public/logo-loader.css, loaded by index.html (so the same loader also shows before any script has run).
// The markup below is kept identical to the first-load splash in index.html (LogoLoader.test.tsx compares them). Reduced motion: the finished logo, still.
export const LOGO_LOADER_SVG_CLASSES = "ll";

/** The person, two poses: stepping (front leg raised) and standing. Feet are at 0,0; the animation moves the group from tread to tread. */
function Person() {
  return (
    <g className="ll-person">
      <g transform="scale(1.32)">
        <circle className="ll-head" cx="1" cy="-30" r="4" />
        <g className="ll-pose ll-pa"><path d="M1 -25 L1 -13 M1 -13 L-1 -6 L-3 0 M1 -13 L8 -13 L10 -6 M1 -22 L-6 -16 M1 -22 L8 -18" /></g>
        <g className="ll-pose ll-pb"><path d="M1 -25 L0 -13 M0 -13 L-3 -6 L-5 0 M0 -13 L3 -6 L5 0 M1 -22 L-5 -15 M1 -22 L6 -16" /></g>
      </g>
    </g>
  );
}

export function LogoMark({ className = "" }: { className?: string }) {
  return (
    <svg className={("ll " + className).trim()} viewBox="0 -14 220 144" aria-hidden="true" focusable="false">
      <g className="ll-all">
        <path className="ll-stairs" pathLength={1} d="M6 118H40V102H72V86H104V70H136V54H166" />
        <rect className="ll-gold ll-stem" x="166" y="30" width="7" height="88" rx="1.5" />
        <rect className="ll-gold ll-foot" x="166" y="111" width="40" height="7" rx="1.5" />
        <rect className="ll-gold ll-base" x="176" y="29" width="34" height="1.6" />
        <rect className="ll-bar ll-b1" x="180" y="20" width="8" height="9" />
        <rect className="ll-bar ll-b2" x="192" y="12" width="8" height="17" />
        <rect className="ll-bar ll-b3" x="204" y="4" width="8" height="25" />
        <path className="ll-arrow" pathLength={1} d="M172 8 Q198 2 213 -9" />
        <path className="ll-head-arrow" d="M219 -14 L206 -9 L214 -3 Z" />
        <Person />
      </g>
    </svg>
  );
}

type Size = "sm" | "md" | "lg" | "xl";

/** `size`: sm (a button or a line of text), md, lg (a section), xl. `wordmark` adds "FinLit" under the logo. `label` is what a screen reader hears. */
export function LogoLoader({ size = "md", label = "Loading", wordmark = false, className = "" }: { size?: Size; label?: string; wordmark?: boolean; className?: string }) {
  return (
    <span className={("ll-stack " + className).trim()} role="status" aria-live="polite">
      <LogoMark className={"ll-" + size} />
      {wordmark && <span className="ll-word" aria-hidden="true">FinLit</span>}
      <span className="ll-sr">{label}</span>
    </span>
  );
}

/** A whole page or section that is still loading: the logo, centred, with a short line under it. */
export function PageLoading({ label = "Loading", size = "lg" }: { label?: string; size?: Size }) {
  return <div className="ll-full"><LogoLoader size={size} label={label} /></div>;
}

/** Beside a line of text, for a small wait ("Calculating…"). */
export function InlineLoading({ children }: { children: React.ReactNode }) {
  return <span className="ll-inline"><LogoLoader size="sm" label="Loading" />{children}</span>;
}
