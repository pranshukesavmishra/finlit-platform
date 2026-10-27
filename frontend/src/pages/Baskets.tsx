// My baskets: the queries a member has saved, with how many companies each matches today. Open one in the Query builder to change it.
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { nf, dateIN } from "../lib/format";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { basketNameProblem, queryPreview, useBasketActions, useBaskets, type Basket } from "../lib/query";
import { useDocTitle } from "../lib/title";
import { TIER, useUI } from "../lib/ui";
import "../styles/qbuilder.css";

const statusText = (b: Basket): string =>
  b.status === "locked" ? "Uses a ratio your plan does not include" : b.status === "invalid" ? "This query needs fixing" : b.count == null ? "Counting…" : `${nf(b.count, 0)} match${b.count === 1 ? "" : "es"}${b.stale ? " (last count)" : ""}`;

function Card({ b, names }: { b: Basket; names: string[] }) {
  const nav = useNavigate();
  const { toast } = useUI();
  const act = useBasketActions();
  const [rename, setRename] = useState<string | null>(null), [confirm, setConfirm] = useState(false), [err, setErr] = useState("");
  const fail = (e: unknown) => setErr(e instanceof ApiError && e.body.detail ? e.body.detail : "That did not work. Please try again.");
  const nameBad = rename != null ? basketNameProblem(rename, names, b.name) : null;
  return (
    <li className="card qb-bk">
      <div className="qb-bkh">
        {rename == null ? <h3>{b.name}</h3> : <form onSubmit={(e) => { e.preventDefault(); if (nameBad) return; setErr(""); act.update.mutate({ id: b.id, name: rename.trim() }, { onSuccess: () => { setRename(null); toast("Renamed."); }, onError: fail }); }}>
          <label className="sr-only" htmlFor={"rn-" + b.id}>New name</label>
          <input id={"rn-" + b.id} autoFocus value={rename} maxLength={80} onChange={(e) => setRename(e.target.value)} aria-invalid={!!nameBad} onKeyDown={(e) => e.key === "Escape" && setRename(null)} />
          <button className="btn primary" type="submit" disabled={!!nameBad || act.update.isPending}>Save</button><button className="btn" type="button" onClick={() => setRename(null)}>Cancel</button></form>}
        <span className={"qb-count-pill " + b.status} aria-live="polite"><b>{b.status === "ok" && b.count != null ? nf(b.count, 0) : "—"}</b><small>{statusText(b)}</small></span>
      </div>
      {nameBad && <p className="qb-err" role="alert">{nameBad}</p>}
      <code className="qb-bkq">{queryPreview(b.query, 200)}</code>
      {b.note && <p className="qb-sub">{b.note}</p>}
      <p className="qb-sub">{b.recent ? "Only recent results · " : ""}Updated {dateIN(b.updatedAt)}{b.leftOut ? ` · ${nf(b.leftOut, 0)} companies left out for missing data` : ""}</p>
      {err && <p className="qb-err" role="alert">{err}</p>}
      <div className="qb-bka">
        <button className="btn primary" onClick={() => nav(`/query-builder?basket=${b.id}`)}>Open</button>
        <button className="btn" onClick={() => { setRename(b.name); setErr(""); }}>Rename</button>
        <button className="btn" disabled={act.duplicate.isPending} onClick={() => { setErr(""); act.duplicate.mutate({ id: b.id }, { onSuccess: (r) => toast(`Made “${r.basket.name}”.`), onError: fail }); }}><Icon name="layers" />Duplicate</button>
        {!confirm ? <button className="btn" onClick={() => setConfirm(true)}><Icon name="trash" />Delete</button>
          : <span className="qb-confirm" role="group" aria-label={`Delete ${b.name}?`}>Delete this basket?<button className="btn" onClick={() => act.remove.mutate(b.id, { onSuccess: () => toast("Basket deleted."), onError: fail })}>Yes, delete</button><button className="btn" onClick={() => setConfirm(false)}>Keep it</button></span>}
      </div>
    </li>
  );
}

export function BasketsPage() {
  useDocTitle("My baskets", "Your saved queries from the Query builder, each with the number of listed companies it matches today.");
  const { user } = useAuth();
  const q = useBaskets(!!user && !DEMO);
  const list = q.data?.baskets ?? [], max = q.data?.max ?? 0;
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">My baskets</div><h1>Your saved queries.</h1>
        <p>A basket is a query you wrote and named. It is your own screen, not a model portfolio: the list changes as company figures change, and each basket shows how many companies match today.</p></div></section>
      <div className="wrap qb">
        {DEMO ? <div className="state"><p>Baskets are part of the live site.</p></div>
          : !user ? <div className="card state"><h2>Sign in to keep baskets</h2><p>Baskets are saved to your account so they are there on any device.</p><Link className="btn primary" to="/login">Sign in</Link></div>
          : q.isLoading ? <div className="skeleton" style={{ height: 180 }} aria-busy="true" />
          : q.isError ? <div className="state"><h2>We could not load your baskets</h2><button className="btn" onClick={() => q.refetch()}>Try again</button></div>
          : <>
            <div className="qb-bkbar"><span aria-live="polite"><b>{list.length}</b> of {max} baskets used{list.length >= max ? <> · <Link className="alx-link" to="/account/plan">More with {TIER[q.data!.plan === "basic" ? "silver" : "gold"].n}</Link></> : null}</span>
              <Link className="btn primary" to="/query-builder">New basket</Link></div>
            {list.length === 0 ? <div className="card state"><h2>No baskets yet</h2><p>Write a query in the Query builder, then choose “Save as basket”. Try an example like “Quality compounders” to see how it works.</p><Link className="btn primary" to="/query-builder">Open the Query builder</Link></div>
              : <ul className="qb-bklist">{list.map((b) => <Card key={b.id} b={b} names={list.map((x) => x.name)} />)}</ul>}
            <p className="faint qb-foot"><Icon name="info" /> Counts use today's data and your current plan. A basket is a list that matches your rules, not advice on what to buy or sell.</p>
          </>}
      </div>
    </>
  );
}
