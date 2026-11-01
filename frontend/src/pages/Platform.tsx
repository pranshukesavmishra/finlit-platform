import { useState } from "react";
import { Link } from "react-router";
import { Reveal } from "../components/Reveal";
import { Icon } from "../lib/icons";
import { PLATFORM_CARDS, PLAN_TIER, TIER_FILTERS, type PlatformCard, type TierFilter } from "../lib/platformCards";
import { useDocTitle } from "../lib/title";

const PRODUCTS: Pick<PlatformCard, "title" | "plan" | "desc" | "cta" | "to">[] = [
  { title: "Company research", plan: "FREE ACCOUNT", desc: "Financial statements, ratios, ownership and peers, with the figures in one company report.", cta: "Explore company reports", to: "/research" },
  { title: "FinLit Prism", plan: "GOLD", desc: "Four financial-health components, separate technical views and the evidence behind every factor.", cta: "Explore FinLit Prism", to: "/prism" },
  ...PLATFORM_CARDS,
];
export function PlatformPage() {
  useDocTitle("Products and research tools", "Explore FinLit company research, Prism, screeners, charts and portfolio tools.");
  const [tier, setTier] = useState<TierFilter>("all");
  const products = PRODUCTS.filter((p) => tier === "all" || PLAN_TIER[p.plan] === tier);
  return <div className="product-directory wrap"><header className="service-hero"><p className="landing-eyebrow">Our products</p><h1>Follow your curiosity.<br />Check the evidence.</h1><p>Choose a tool for the question you want to answer. Start free and go deeper when you need to.</p><Link className="marketing-action marketing-action-primary" to="/plans">Compare plans <Icon name="arrow" /></Link></header>
    <div className="directory-filter" role="group" aria-label="Filter products by plan">{TIER_FILTERS.map((t) => <button key={t.k} data-tier={t.k === "all" ? undefined : t.k} aria-pressed={tier === t.k} onClick={() => setTier(t.k)}>{t.label}</button>)}</div>
    <div className="directory-list">{products.map((p, i) => <Reveal key={p.to}><Link className="directory-product" data-tier={PLAN_TIER[p.plan]} to={p.to}><span className="landing-index">{String(i + 1).padStart(2, "0")}</span><div><span className="directory-plan membership-badge">{p.plan === "FREE ACCOUNT" ? "Basic · free" : p.plan === "SILVER" ? "Silver" : "Gold"}</span><h2>{p.title}</h2><p>{p.desc}</p></div><span className="directory-open">{p.cta}<Icon name="arrow" /></span></Link></Reveal>)}</div>
    <p className="landing-caption directory-note">Some tools have different limits by plan. Access details are shown when you open them. Research is for information, not investment advice.</p>
  </div>;
}
