// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { ChartZoom, useChartZoomed } from "./ChartZoom";

afterEach(() => { cleanup(); document.body.style.overflow = ""; });

function Counter() {
  const [n, setN] = useState(0);
  const z = useChartZoomed();
  return <div data-testid="chart"><svg role="img" aria-label="demo" viewBox="0 0 10 10" /><button onClick={() => setN(n + 1)}>range {n}</button><span>{z ? "big" : "small"}</span></div>;
}

describe("ChartZoom", () => {
  it("shows one enlarge arrow with an accessible name, and no dialog until it is pressed", () => {
    render(<ChartZoom label="Revenue"><Counter /></ChartZoom>);
    const b = screen.getByRole("button", { name: "Enlarge chart: Revenue" });
    expect(b.getAttribute("aria-haspopup")).toBe("dialog");
    expect(b.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows no arrow while there is only a skeleton or a note, and none for a decorative icon", () => {
    render(<ChartZoom label="Empty"><p>Not available yet.</p><svg viewBox="0 0 16 16" aria-hidden="true" /></ChartZoom>);
    expect(screen.queryByRole("button", { name: /Enlarge chart/ })).toBeNull();
  });

  it("opens the same chart in a labelled modal dialog and locks page scroll", () => {
    render(<ChartZoom label="Revenue"><Counter /></ChartZoom>);
    fireEvent.click(screen.getByRole("button", { name: "Enlarge chart: Revenue" }));
    const d = screen.getByRole("dialog", { name: "Revenue" });
    expect(d.getAttribute("aria-modal")).toBe("true");
    expect(d.contains(screen.getByTestId("chart"))).toBe(true);
    expect(screen.getAllByTestId("chart")).toHaveLength(1);
    expect(screen.getByText("big")).toBeTruthy();
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("keeps the chart's own state when it moves into the dialog and back", () => {
    render(<ChartZoom label="Revenue"><Counter /></ChartZoom>);
    fireEvent.click(screen.getByText("range 0"));
    fireEvent.click(screen.getByRole("button", { name: "Enlarge chart: Revenue" }));
    expect(screen.getByText("range 1")).toBeTruthy();
    fireEvent.click(screen.getByText("range 1"));
    fireEvent.click(screen.getByRole("button", { name: "Restore chart: Revenue" }));
    expect(screen.getByText("range 2")).toBeTruthy();
    expect(screen.getByText("small")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body.style.overflow).toBe("");
  });

  it("Escape closes it and focus returns to the arrow", () => {
    render(<ChartZoom label="Revenue"><Counter /></ChartZoom>);
    const b = screen.getByRole("button", { name: "Enlarge chart: Revenue" });
    b.focus();
    fireEvent.click(b);
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(document.activeElement && screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(b);
  });

  it("a click on the dimmed page closes it", () => {
    const { container } = render(<ChartZoom label="Revenue"><Counter /></ChartZoom>);
    fireEvent.click(screen.getByRole("button", { name: "Enlarge chart: Revenue" }));
    fireEvent.click(document.querySelector(".cz-scrim")!);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(container.querySelector(".cz-host [data-testid=chart]")).toBeTruthy();
  });

  it("Tab stays inside the dialog", () => {
    render(<ChartZoom label="Revenue"><Counter /></ChartZoom>);
    fireEvent.click(screen.getByRole("button", { name: "Enlarge chart: Revenue" }));
    const d = screen.getByRole("dialog");
    const items = d.querySelectorAll<HTMLElement>("button");
    items[items.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(d.contains(document.activeElement)).toBe(true);
  });

  it("a chart inside another ChartZoom gets no second arrow", () => {
    render(<ChartZoom label="Card"><ChartZoom label="Inner"><Counter /></ChartZoom></ChartZoom>);
    expect(screen.getAllByRole("button", { name: /Enlarge chart/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Enlarge chart: Card" })).toBeTruthy();
  });
});

describe("ChartZoom arrow placement", () => {
  const card = { border: "1px solid #444", borderRadius: 12 } as const;
  it("anchors the arrow to the card that holds only this chart, and keeps the title row clear of it", () => {
    render(<div style={card} data-testid="card"><div data-testid="head">Title</div><ChartZoom label="Revenue"><Counter /></ChartZoom></div>);
    const btn = screen.getByRole("button", { name: "Enlarge chart: Revenue" });
    expect(btn.className).toContain("cz-at-box");
    expect(btn.parentElement?.className).toContain("cz-boxed");
    expect(screen.getByTestId("head").hasAttribute("data-cz-head")).toBe(true);
  });
  it("gives the arrow a strip of its own when the card has no title row above the chart", () => {
    render(<div style={card}><ChartZoom label="Revenue"><Counter /></ChartZoom></div>);
    expect(screen.getByRole("button", { name: "Enlarge chart: Revenue" }).parentElement?.className).toContain("cz-strip");
  });
  it("leaves the arrow at the chart's own corner when the card holds several charts", () => {
    render(<div style={card}><ChartZoom label="One"><Counter /></ChartZoom><ChartZoom label="Two"><Counter /></ChartZoom></div>);
    const btn = screen.getByRole("button", { name: "Enlarge chart: One" });
    expect(btn.className).not.toContain("cz-at-box");
    expect(btn.parentElement?.className).not.toContain("cz-boxed");
  });
  it("removes the title-row mark when the chart goes away", () => {
    const { unmount } = render(<div style={card}><div data-testid="head">Title</div><ChartZoom label="Revenue"><Counter /></ChartZoom></div>);
    const head = screen.getByTestId("head");
    unmount();
    expect(head.hasAttribute("data-cz-head")).toBe(false);
  });
});
