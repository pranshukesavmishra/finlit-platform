import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { prefetchMarkets, useGold } from "../lib/premium";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import type { ReactNode } from "react";

const CARDS = [
  { to: "/premium/fundamentals", icon: "table", title: "Stock Fundamental Data Dashboard", text: "Every statement, ratio and shareholder of a listed company, in one place.",
    points: ["Income statement, balance sheet and cash flow", "Named shareholders and promoter pledge", "Peers, dividends and corporate actions"] },
  { to: "/premium/markets", icon: "activity", title: "Market Events & Index Dashboard", text: "What is happening in the market this week, and how the indices and commodities are valued.",
    points: ["IPO and results calendars", "Announcements and call transcripts", "Index prices, valuation history and commodities"] },
  { to: "/premium/report", icon: "notes", title: "Premium Report", text: "A clean, printable research report for any company. Save it as a PDF to share.",
    points: ["FinLit score and what drives it", "Key ratios, ownership and peers", "One page you can print or save"] },
];

/** Locked view for people not on Gold: what the dashboard holds and one clear way to unlock it. */
export function GoldLock({ title }: { title: string }) {
  const { upgrade } = useUI();
  return (
    <div className="wrap" style={{ padding: "56px 0" }}>
      <div className="pm-lock"><span className="tier gold"><Icon name="crown" />Gold plan</span><h2>{title}</h2>
        <p>This dashboard is part of the Gold plan. Gold members get the full research tools, live market events and the complete fundamentals of every company.</p>
        <button className="btn primary" onClick={() => upgrade("gold", `${title} is part of Gold.`)}>Unlock with Gold <Icon name="arrow" /></button>
        <p style={{ marginTop: 14 }}><Link to="/plans">Compare plans</Link></p></div>
    </div>
  );
}

export function PremiumHead({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
    <div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{children}</div></section>;
}

export function PremiumHub() {
  useDocTitle("Gold dashboards", "Stock fundamentals, market events and index dashboards, and printable premium reports for FinLit Gold members.");
  const gold = useGold(); const qc = useQueryClient();
  return (
    <>
      <PremiumHead eyebrow="Gold dashboards" title="The premium research desk."><p>Three tools built for serious investors. They open fast, stay up to date, and every number comes from the same sources our analysts use.</p></PremiumHead>
      <div className="wrap" style={{ paddingBottom: 56 }}>
        {!gold && <p className="chip gold" style={{ height: "auto", padding: "8px 14px", whiteSpace: "normal", maxWidth: "100%", lineHeight: 1.4 }}><Icon name="crown" /> Included with the Gold plan. Open any tool to see how it works.</p>}
        <div className="pm-hub">
          {CARDS.map((c) => (
            <Link key={c.to} to={c.to} className="pm-card" onMouseEnter={() => gold && c.to.endsWith("markets") && prefetchMarkets(qc)}>
              <span className="ic"><Icon name={c.icon} /></span><h2>{c.title}</h2><p>{c.text}</p>
              <ul>{c.points.map((p) => <li key={p}><Icon name="check" />{p}</li>)}</ul>
              <span className="go">Open <Icon name="arrow" /></span>
            </Link>))}
        </div>
      </div>
    </>
  );
}
