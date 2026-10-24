import { Component, type ReactNode } from "react";

/** Wraps a 3D scene: if its code fails to load or throws while rendering, the scene is left out and the page carries on without it. */
export class Safe3D extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(e: unknown) { console.warn("3D scene left out:", e instanceof Error ? e.message : e); }
  render() { return this.state.failed ? null : this.props.children; }
}
