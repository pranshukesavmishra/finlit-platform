import { Link } from "react-router";
import { NotifyForm } from "../components/NotifyForm";
import { useDocTitle } from "../lib/title";
import "../styles/f3.css";

export function FinancialProduct() {
  useDocTitle("Financial product", "A FinLit financial product is being prepared. Leave your email to be told the day it is ready.");
  return (
    <section className="sec"><div className="wrap fp" aria-labelledby="fpT"><div>
      <div className="hh-kicker">Financial product</div>
      <h1 id="fpT">Coming soon</h1>
      <p>We are still preparing this. Nothing is on offer yet, and it may need approvals before it can be. Leave your email and we will write to you once, the day it is ready.</p>
      <NotifyForm source="financial-product" />
      <p className="faint" style={{ fontSize: 12.5, marginTop: 18 }}>Information only, not investment advice. <Link to="/">Back to the home page</Link></p>
    </div></div></section>
  );
}
