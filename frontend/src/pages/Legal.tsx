import { Link, useParams } from "react-router";
import { COMPANY } from "../content/site";
import { useDocTitle } from "../lib/title";

const DOCS: Record<string, { title: string; body: [string, string][] }> = {
  terms: { title: "Terms of use", body: [
    ["Who we are", `${COMPANY.name} ("FinLit") provides investment research information, portfolio reviews and planning conversations through this website.`],
    ["Information, not advice", COMPANY.disclaimer + " Nothing on this site is an offer or recommendation to buy, sell or hold any security."],
    ["Using the site", "You may use the site for your own personal, lawful purposes. Do not scrape it, attempt to break its security, or resell its data."],
    ["Accuracy", "We check data before publishing, but figures come from company filings and market data providers and may be delayed or wrong. Verify before you act."],
    ["Plans and payments", "Paid plans, when launched, are billed through Razorpay. Prices and features may change; changes are announced before they apply."],
    ["Liability", "To the extent the law allows, FinLit is not liable for losses arising from decisions made using the site."],
    ["Contact", `Questions: ${COMPANY.email}.`],
  ] },
  privacy: { title: "Privacy notice", body: [
    ["What we collect", "Details you give us (name, email, mobile, messages) when you contact us, enquire about a service or create an account, and basic usage data needed to run and secure the site."],
    ["Why", "To reply to you, deliver services, keep the site secure and improve it. We ask for your consent where the law requires it, and you can withdraw it at any time."],
    ["Sign-in", "We do not store passwords. Sign-in uses a one-time email code, Google sign-in or a passkey."],
    ["Payments", "Card and UPI details go to Razorpay. We never see or store them."],
    ["Who sees it", "Service providers who help us run the site (hosting, email delivery, error monitoring), under agreements that limit how they use it. We do not sell personal data."],
    ["Where it is stored", "Primary data is stored in India. Encrypted backups may be held with a cloud provider outside India."],
    ["Your rights", `You can ask to access, correct, export or delete your data, or withdraw consent, by writing to ${COMPANY.email}.`],
    ["Retention", "We keep data only as long as needed for the purposes above or as the law requires."],
  ] },
  disclosures: { title: "Research disclosures", body: [
    ["Not a registered adviser", COMPANY.disclaimer],
    ["How scores are made", "Research scores, summaries and notes are produced by automated models, including AI, from company filings and market data. They can be wrong or out of date."],
    ["Model", "The FinLit score averages five pillars (quality, growth, profitability, balance sheet, technical). Each input is mapped to a score using published thresholds. The method is explained on every stock page."],
    ["Conflicts", "Team members may hold securities discussed on this site. Portfolio results shown are realised results from a broker statement and are not a promise of future returns."],
    ["Risk", "Investments in securities markets are subject to market risks. Read all related documents carefully before investing."],
  ] },
};

export function Legal() {
  const { doc = "terms" } = useParams();
  const d = DOCS[doc];
  useDocTitle(d?.title || "Legal");
  if (!d) return <div className="wrap state"><h2>Page not found</h2></div>;
  return (
    <section className="sec"><div className="wrap legal">
      <div className="eyebrow">Legal</div><h1 style={{ font: "300 clamp(32px,5vw,52px)/1.1 var(--serif)", margin: "8px 0 8px" }}>{d.title}</h1>
      <p className="faint">Draft for review by FinLit's legal adviser before launch. Last updated October 2026.</p>
      {d.body.map(([h, t]) => <div key={h}><h2>{h}</h2><p>{t}</p></div>)}
      <p style={{ marginTop: 32 }}>{Object.keys(DOCS).filter((k) => k !== doc).map((k) => <Link key={k} to={`/legal/${k}`} style={{ marginRight: 16 }}>{DOCS[k].title}</Link>)}</p>
    </div></section>
  );
}

export function NotFound() {
  useDocTitle("Page not found");
  return <div className="wrap state"><h2>We can't find that page</h2><p>It may have moved. Try the research search or head home.</p><Link className="btn primary" to="/">Go home</Link></div>;
}
