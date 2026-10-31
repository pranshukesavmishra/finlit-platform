import { Component, type ReactNode } from "react";
import { isChunkError, reloadOnce, reportError } from "../lib/resilience";

/** Keeps one broken block from blanking the whole page. `section` shows a small note in place; the default shows a full-page message. */
export class ErrorBoundary extends Component<{ children: ReactNode; section?: string; message?: string }, { failed: boolean; stale: boolean }> {
  state = { failed: false, stale: false };
  static getDerivedStateFromError(error: unknown) { return { failed: true, stale: isChunkError(error) }; }
  componentDidCatch(error: unknown) {
    console.error("render failed", error);
    reportError(error, isChunkError(error) ? "chunk" : "render");
    if (isChunkError(error) && !this.props.section) reloadOnce();   // a page file of an older release is gone: load the new release
  }
  render() {
    if (!this.state.failed) return this.props.children;
    if (this.props.message) return <article className="card"><p className="faint" role="status">{this.props.message}</p></article>;
    if (this.props.section) return (
      <section className="block"><p className="faint" role="status">{this.props.section} is not available for this company right now.</p></section>
    );
    const home = import.meta.env.BASE_URL.replace(/\/$/, "");   // plain links on purpose: this card must work even when the router itself failed
    return (
      <div style={{ padding: "72px 16px", display: "grid", placeItems: "center" }}>
        <article className="card" role="alert" style={{ maxWidth: 520, width: "100%", padding: 28, textAlign: "center" }}>
          <h1 style={{ fontSize: 24, margin: "0 0 10px" }}>{this.state.stale ? "A new version of FinLit is ready" : "Something went wrong on this page"}</h1>
          <p className="muted" style={{ margin: "0 0 18px" }}>{this.state.stale ? "The site was just updated. Reloading brings you the new version." : "Your data is safe. Reload the page, or go back to your dashboard. If it keeps happening, tell us on the contact page."}</p>
          <p style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap", margin: 0 }}>
            <button className="btn primary" onClick={() => location.reload()}>Reload</button>
            <a className="btn" href={`${home}/dashboard`}>Go to dashboard</a>
          </p>
        </article>
      </div>
    );
  }
}
