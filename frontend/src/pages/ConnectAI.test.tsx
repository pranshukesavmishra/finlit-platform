// @vitest-environment jsdom
// The "Connect AI assistants" page: the address comes from the site's own origin, every tool is listed once, every client has its steps,
// the limits and the disclaimer are there, and the page promises nothing it cannot keep (no advice words, no pretence of OAuth).
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { ConnectAIPage } from "./ConnectAI";
import { MCP_DISCLAIMER, MCP_LIMITS, MCP_TOOLS, claudeCodeCommand, cursorConfig, mcpEndpoint } from "../lib/mcpTools";
import { MORE } from "../lib/nav";

afterEach(cleanup);
const show = () => render(<MemoryRouter initialEntries={["/mcp"]}><ConnectAIPage /></MemoryRouter>);

describe("Connect AI assistants page", () => {
  it("shows the endpoint built from the site's own address", () => {
    show();
    const url = `${window.location.origin}/mcp`;
    expect(url).toMatch(/^https?:\/\/.+\/mcp$/);
    expect(screen.getAllByText(url).length).toBeGreaterThan(0);
    expect(mcpEndpoint("https://finlitventures.com/")).toBe("https://finlitventures.com/mcp");
  });

  it("gives the exact setup for Claude, ChatGPT, Cursor and Claude Code", () => {
    const { container } = show();
    const url = `${window.location.origin}/mcp`;
    const text = container.textContent ?? "";
    for (const h of ["Claude (claude.ai and Claude Desktop)", "ChatGPT", "Cursor", "Claude Code"]) expect(screen.getByRole("heading", { name: h })).toBeTruthy();
    expect(text).toContain("Add custom connector");
    expect(text).toContain("Create app");
    expect(text).toContain(".cursor/mcp.json");
    expect(container.querySelector("pre")?.textContent).toBe(url);
    const codes = [...container.querySelectorAll("pre code")].map((c) => c.textContent);
    expect(codes).toContain(`claude mcp add --transport http finlit ${url}`);
    const cursor = JSON.parse(codes.find((c) => c?.includes("mcpServers")) as string);
    expect(cursor).toEqual({ mcpServers: { finlit: { url } } });
    expect(claudeCodeCommand("U")).toBe("claude mcp add --transport http finlit U");
    expect(JSON.parse(cursorConfig("U")).mcpServers.finlit.url).toBe("U");
  });

  it("lists every tool once, and says it is read-only", () => {
    const { container } = show();
    const names = MCP_TOOLS.map((t) => t.name);
    expect(new Set(names).size).toBe(names.length);
    expect(names.length).toBe(20);
    const listed = [...container.querySelectorAll(".ca-tools code")].map((c) => c.textContent);
    expect(listed.sort()).toEqual([...names].sort());
    expect(screen.getByRole("heading", { name: "The tools (20)" })).toBeTruthy();
    expect(container.textContent).toContain("read-only");
    for (const bad of ["add_", "delete_", "remove_", "watchlist", "portfolio_"]) expect(names.some((n) => n.includes(bad)), bad).toBe(false);
  });

  it("states the limits, freshness, the missing-data rule, the OAuth fact and the disclaimer", () => {
    const { container } = show();
    const text = (container.textContent ?? "").replace(/\s+/g, " ");
    expect(text).toContain(`${MCP_LIMITS.perMinute} requests a minute`);
    expect(text).toContain("1,000 tool calls a day");
    expect(text).toContain("unauthenticated");
    expect(text).toContain("OAuth");
    expect(text).toContain("never filled with zero or an estimate");
    expect(text).toContain("How fresh the data is");
    expect(text).toContain(MCP_DISCLAIMER);
    expect(text).toContain("not registered with SEBI or AMFI");
  });

  it("uses no investment-advice wording", () => {
    const { container } = show();
    const text = (container.textContent ?? "").toLowerCase();
    for (const w of ["buy", "sell", "accumulate", "price target", "target price", "recommend you"]) expect(new RegExp(`\\b${w}\\b`).test(text), w).toBe(false);
  });

  it("has a test prompt and a copy button for each block", () => {
    show();
    const copies = screen.getAllByRole("button", { name: /^Copy/ });
    expect(copies.length).toBe(4);   // the address, the Cursor file, the Claude Code command, the test prompt
    const section = screen.getByRole("heading", { name: "Try it" }).parentElement!;
    expect(within(section).getAllByText(/Using the FinLit tools/).length).toBe(1);
  });

  it("is linked from the More menu", () => {
    const item = MORE.groups.flatMap((g) => g.items).find((i) => i.to === "/mcp");
    expect(item?.label).toBe("Connect AI assistants");
  });
});
