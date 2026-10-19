import { Component, type ReactNode } from "react";

/** Keeps one broken block from blanking the whole page. `section` shows a small note in place; the default shows a full-page message. */
export class ErrorBoundary extends Component<{ children: ReactNode; section?: string }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: unknown) { console.error("render failed", error); }
  render() {
    if (!this.state.failed) return this.props.children;
    if (this.props.section) return (
      <section className="block"><p className="faint" role="status">{this.props.section} is not available for this company right now.</p></section>
    );
    return (
      <div style={{ padding: "96px 24px", textAlign: "center" }}>
        <h1>Something went wrong on this page</h1>
        <p>Please reload, or go back to the <a href="/">home page</a>. If it keeps happening, tell us on the contact page.</p>
        <p><button className="btn" onClick={() => location.reload()}>Reload</button></p>
      </div>
    );
  }
}
