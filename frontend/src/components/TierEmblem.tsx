import { useId } from "react";

/** Decorative tier artwork for the plan banners: a silver medal and a gold crown, drawn in the tier colours (--t-silver, --t-gold) so both themes follow. */
export function TierEmblem({ tier }: { tier: "silver" | "gold" }) {
  const g = useId().replace(/:/g, "") + tier;
  return (
    <svg className="pg-emblem" viewBox="0 0 96 96" aria-hidden="true" role="presentation" focusable="false">
      <defs><linearGradient id={g} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--tc)" stopOpacity=".95" /><stop offset="1" stopColor="var(--tc)" stopOpacity=".55" /></linearGradient></defs>
      <circle cx="48" cy="48" r="45" fill="var(--tc)" opacity=".12" />
      <circle cx="48" cy="48" r="45" fill="none" stroke="var(--tc)" strokeOpacity=".4" strokeWidth="1.5" />
      {tier === "silver" ? <g>
        <path d="M33 14h12l7 22H40z" fill="var(--tc)" opacity=".45" /><path d="M51 14h12L52 38H44z" fill="var(--tc)" opacity=".7" />
        <circle cx="48" cy="58" r="22" fill={`url(#${g})`} /><circle cx="48" cy="58" r="16.5" fill="none" stroke="var(--s1)" strokeOpacity=".75" strokeWidth="2" />
        <path d="m48 48 3.1 6.3 6.9 1-5 4.9 1.2 6.9-6.2-3.3-6.2 3.3 1.2-6.9-5-4.9 6.9-1z" fill="var(--s1)" opacity=".92" />
      </g> : <g>
        <path d="M22 66 17 34l17 15 14-24 14 24 17-15-5 32z" fill={`url(#${g})`} stroke="var(--tc)" strokeWidth="1.5" strokeLinejoin="round" />
        <rect x="22" y="68" width="52" height="8" rx="3" fill="var(--tc)" />
        <circle cx="17" cy="33" r="4" fill="var(--tc)" /><circle cx="48" cy="23" r="4.5" fill="var(--tc)" /><circle cx="79" cy="33" r="4" fill="var(--tc)" />
        <circle cx="48" cy="55" r="4" fill="var(--s1)" opacity=".9" /><circle cx="34" cy="58" r="2.6" fill="var(--s1)" opacity=".8" /><circle cx="62" cy="58" r="2.6" fill="var(--s1)" opacity=".8" />
      </g>}
    </svg>
  );
}
