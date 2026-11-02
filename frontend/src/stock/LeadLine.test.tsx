// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ body: null as unknown }));
vi.mock("../lib/api", async (orig) => ({ ...(await orig<typeof import("../lib/api")>()), apiGet: vi.fn(async () => st.body) }));
import { LeadLine } from "./Leadership";

const on = (o: Record<string, unknown> = {}) => ({
  available: true, asOf: "2026-10-30", stale: false, held: false, rank: 9, label: "laggard", rawLabel: "laggard", direction: "weakening", fundamentalNote: null, fundamentalRank: null, fundamentalOf: null, labelSince: null,
  peerGroup: { id: "x", name: "Peers", short: "peers", kind: "industry", ranked: 10 }, benchmarks: { sector: { code: null, name: "peer average", kind: "peer_average", ret52: null }, market: null },
  rel: { w13: null, w26: null, w52: null, w52Market: null }, sectorReliability: { tier: "insufficient", hitRate6m: null, checks: 0, from: null, to: null, periods: [] }, peers: [],
  display: { chip: "Laggard", line: "9th of 10 peers", tooltip: "t", parts: { rank: "9th of 10 peers", sector: { pts: "−23.2", name: "peer average", v: -0.2 }, market: { pts: "−33.0", name: "Nifty Midcap 150", v: -0.3 }, direction: "weakening" },
    note: "Business score ranks 3rd of 10, stronger than the price", benchmarkNote: "There is no matching sector index, so the average return of the peers stands in for it.", ...o }, ...{} });
const show = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><LeadLine symbol="MAZDOCK" jump={() => undefined} /></MemoryRouter></QueryClientProvider>);
afterEach(cleanup);

describe("the leadership strip under a company's name", () => {
  it("is one row of cells (label and rank, the figures, the direction) with the notes in their own row beneath", async () => {
    st.body = on();
    const { container } = show();
    await screen.findByText("9th of 10 peers");
    const row = container.querySelector(".ld-row")!;
    const cells = [...row.children].map((c) => c.className.split(" ")[0]);
    expect(cells.slice(0, 3)).toEqual(["ld-a", "ld-b", "ld-dir"]);
    expect(row.querySelector(".ld-dir")!.textContent).toContain("weakening over 3 months");
    expect(row.querySelector(".ld-b")!.textContent).toContain("(12 months)");
    const notes = container.querySelector(".ld-notes")!;
    expect(notes.parentElement).toBe(container.querySelector(".ld-line"));
    expect(notes.querySelector(".ld-caution")!.textContent).toContain("Business score ranks 3rd of 10");
    expect(notes.textContent).toContain("There is no matching sector index");
  });
  it("shows no direction cell when there is no direction, and no notes row content when there are no notes", async () => {
    st.body = on({ parts: { rank: "9th of 10 peers", sector: { pts: "−1.0", name: "peer average", v: -0.1 }, market: null, direction: null }, note: null, benchmarkNote: undefined });
    const { container } = show();
    await screen.findByText("9th of 10 peers");
    expect(container.querySelector(".ld-dir")).toBeNull();
    expect(container.querySelector(".ld-notes")!.children.length).toBe(0);
  });
});
