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
    return (
      <div style={{ padding: "96px 24px", textAlign: "center" }}>
        <h1>{this.state.stale ? "A new version of FinLit is ready" : "Something went wrong on this page"}</h1>
        <p>{this.state.stale ? "The site was just updated. Reloading brings you the new version." : <>Please reload, or go back to the <a href="/">home page</a>. If it keeps happening, tell us on the contact page.</>}</p>
        <p><button className="btn" onClick={() => location.reload()}>Reload</button></p>
      </div>
    );
  }
}
