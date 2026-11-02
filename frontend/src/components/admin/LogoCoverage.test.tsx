// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ sent: [] as { method: string; path: string; body: unknown }[], toast: vi.fn() }));
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiGet: vi.fn(async () => ({
    companies: 5800, withLogo: 4100, top500: 500, top500WithLogo: 470,
    items: [{ symbol: "SBIN", name: "State Bank of India", marketCapCr: 887077, status: "blocked", reason: "Its website blocks automated requests, so nothing was fetched." },
            { symbol: "526775", name: "Valiant Communications Ltd", marketCapCr: 1200, status: "untried", reason: "No website is stored for this company, so there is nowhere to look for an icon." }],
  })),
  apiSend: vi.fn(async (method: string, path: string, body: unknown) => { st.sent.push({ method, path, body }); return { status: "manual" }; }),
}));
vi.mock("../../lib/ui", () => ({ useUI: () => ({ toast: st.toast }) }));
import { LogoCoverage, readImage } from "./LogoCoverage";

const wrap = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><LogoCoverage /></QueryClientProvider>);
beforeEach(() => { st.sent = []; st.toast.mockReset(); });
afterEach(cleanup);
const file = (bytes: number, name = "logo.png") => new File([new Uint8Array(bytes)], name, { type: "image/png" });

describe("company logo coverage", () => {
  it("says how much is covered and why each company has no logo", async () => {
    wrap();
    await screen.findByText("SBIN");
    expect(screen.getByText(/4,100 of 5,800 companies have a logo/)).toBeTruthy();
    expect(screen.getByText(/Of the 500 largest, 470 do/)).toBeTruthy();
    expect(screen.getByText("Its website blocks automated requests, so nothing was fetched.")).toBeTruthy();
    expect(screen.getByText(/No website is stored for this company/)).toBeTruthy();
  });
  it("sends the chosen image for that company, as base64", async () => {
    wrap();
    await screen.findByText("SBIN");
    fireEvent.change(screen.getByLabelText("Logo file for SBIN"), { target: { files: [file(2000)] } });
    await waitFor(() => expect(st.sent.length).toBe(1));
    const b = st.sent[0].body as { symbol: string; image: string };
    expect(st.sent[0].method).toBe("POST"); expect(st.sent[0].path).toBe("/api/logos/admin/manual"); expect(b.symbol).toBe("SBIN");
    expect(typeof b.image).toBe("string"); expect(b.image.length).toBeGreaterThan(100);
    await waitFor(() => expect(st.toast).toHaveBeenCalledWith("Logo saved for SBIN."));
  });
  it("refuses a file over 64 KB at once, with the reason, and sends nothing", async () => {
    await expect(readImage(file(70 * 1024))).rejects.toThrow(/at most 64 KB/);
    wrap();
    await screen.findByText("SBIN");
    fireEvent.change(screen.getByLabelText("Logo file for SBIN"), { target: { files: [file(70 * 1024)] } });
    await screen.findByText(/at most 64 KB/);
    expect(st.sent.length).toBe(0);
  });
});
