// @vitest-environment jsdom
// The forum is split by plan: what a visitor, a Gold member and a moderator see on the index page.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ me: {} as Record<string, unknown>, calls: [] as string[] }));
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiGet: async (url: string) => {
    st.calls.push(url);
    if (url.startsWith("/api/forum/me")) return st.me;
    if (url.startsWith("/api/forum/companies")) return { companies: [] };
    return { threads: [], total: 0, page: 1, per: 20, pages: 1, sort: "active", symbol: null, board: st.me.board };
  },
}));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: null, ready: true, isAdmin: false }) }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
import { ForumPage } from "./Forum";

const me = (over: Record<string, unknown>) => ({ signedIn: true, plan: "basic", board: "basic", handle: "asha_k", canPost: true, banned: false, moderator: false, rules: {}, ...over });
const open = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={["/forum"]}><Routes><Route path="forum/*" element={<ForumPage />} /></Routes></MemoryRouter></QueryClientProvider>);

beforeEach(() => { st.calls = []; });
afterEach(cleanup);

describe("forum boards by plan", () => {
  it("a visitor sees no board, only the note to sign in, and no discussion is requested", async () => {
    st.me = me({ signedIn: false, plan: null, board: null, handle: null, canPost: false });
    open();
    expect(await screen.findByText(/Each plan has its own board/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toContain("/login");
    expect(screen.queryByPlaceholderText("Search titles")).toBeNull();
    expect(st.calls.some((c) => c.startsWith("/api/forum/threads"))).toBe(false);
  });
  it("a Gold member is told they are on the Gold board and only Gold members read it", async () => {
    st.me = me({ plan: "gold", board: "gold" });
    open();
    expect(await screen.findByText("Gold board.")).toBeTruthy();
    expect(screen.getByText(/Only Gold members can read and reply here/)).toBeTruthy();
    await waitFor(() => expect(st.calls.some((c) => c.startsWith("/api/forum/threads"))).toBe(true));
    expect(st.calls.find((c) => c.startsWith("/api/forum/threads"))).not.toContain("board=");   // members never ask for another board
  });
  it("a Basic member is on the Basic board", async () => {
    st.me = me({});
    open();
    expect(await screen.findByText("Basic board.")).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Board" })).toBeNull();   // only moderators can switch boards
  });
  it("a moderator can switch between the three boards", async () => {
    st.me = me({ moderator: true });
    open();
    const group = await screen.findByRole("group", { name: "Board" });
    expect(group.querySelectorAll("button").length).toBe(3);
  });
});
