import { useState } from "react";
import { Link } from "react-router";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { MCP_DISCLAIMER, MCP_LIMITS, MCP_TEST_PROMPT, MCP_TOOLS, claudeCodeCommand, cursorConfig, mcpEndpoint } from "../lib/mcpTools";
import { useDocTitle } from "../lib/title";
import "../styles/connectai.css";

function Copy({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  const copy = () => { try { void navigator.clipboard.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1800); }); } catch { /* the text is selectable anyway */ } };
  return <button type="button" className="btn ca-copy" onClick={copy} aria-label={label}>{done ? "Copied" : "Copy"}</button>;
}

function Block({ text, label }: { text: string; label: string }) {
  return <div className="ca-code"><pre tabIndex={0}><code>{text}</code></pre><Copy text={text} label={label} /></div>;
}

const GROUPS = ["Stocks", "Markets", "Funds", "System"] as const;

export function ConnectAIPage() {
  useDocTitle("Connect AI assistants", "Free, read-only Indian stock, fund and market data for Claude, ChatGPT, Cursor and other AI assistants, through the Model Context Protocol (MCP).");
  const url = mcpEndpoint(typeof window === "undefined" ? "https://your-finlit-site" : window.location.origin);
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="about" /><div className="eyebrow">For AI assistants</div><h1>Connect AI assistants to FinLit data.</h1>
        <p>A free, read-only data connection (an MCP server) so an AI assistant can look up Indian company prices, financial statements, ratios, shareholding, results, funds and market figures from FinLit, instead of guessing them.</p></div></section>

      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap ca">
        <h2>Your connection address</h2>
        <Block text={url} label="Copy the FinLit MCP address" />
        <p className="muted">It speaks MCP over HTTP (Streamable HTTP, no sessions). It is free, needs no sign-in and no key, and only reads data: there is nothing in it that can change an account, a watchlist or a portfolio. It gives an assistant exactly what a visitor without an account sees on this site, so figures that sit behind a paid plan stay behind it.</p>
        <p className="ca-note"><b>No sign-in (OAuth) yet.</b> This public server is unauthenticated. An assistant or app that insists on OAuth for every remote server cannot connect to it; use a client that supports plain remote MCP servers, such as the ones below.</p>

        <h2>Set it up</h2>
        <div className="ca-steps">
          <article className="ca-step"><h3>Claude (claude.ai and Claude Desktop)</h3>
            <ol><li>Open <b>Settings</b>, then <b>Connectors</b>.</li><li>Choose <b>Add custom connector</b>.</li><li>Name it FinLit, paste the address above, and add it. Leave any sign-in fields empty.</li><li>In a chat, switch the FinLit connector on from the tools menu.</li></ol></article>
          <article className="ca-step"><h3>ChatGPT</h3>
            <ol><li>Open <b>Settings</b>, then <b>Apps</b> (turn on <b>Developer mode</b> under advanced settings if you do not see it).</li><li>Choose <b>Create app</b>, name it FinLit, and paste the address above as the MCP server URL.</li><li>Set authentication to <b>No authentication</b>, create it, then enable it in a new chat.</li></ol>
            <p className="muted">Availability of developer mode depends on your ChatGPT plan and changes from time to time.</p></article>
          <article className="ca-step"><h3>Cursor</h3>
            <p>Add this to <code>.cursor/mcp.json</code> in your project, or to <code>~/.cursor/mcp.json</code> for all projects:</p>
            <Block text={cursorConfig(url)} label="Copy the Cursor configuration" /></article>
          <article className="ca-step"><h3>Claude Code</h3>
            <p>Run this once in a terminal:</p>
            <Block text={claudeCodeCommand(url)} label="Copy the Claude Code command" /></article>
        </div>

        <h2>Try it</h2>
        <p>Paste this into a chat with FinLit switched on. A correct answer shows dates beside the figures and says where something is missing.</p>
        <Block text={MCP_TEST_PROMPT} label="Copy the test prompt" />

        <h2>The tools ({MCP_TOOLS.length})</h2>
        <p className="muted">Every tool is read-only. Every answer carries its source, an as-of date and a short disclaimer.</p>
        <div className="ca-tools">{GROUPS.map((g) => (
          <div key={g}><h3>{g}</h3><ul>{MCP_TOOLS.filter((t) => t.group === g).map((t) => <li key={t.name}><code>{t.name}</code><span>{t.what}</span></li>)}</ul></div>
        ))}</div>

        <h2>Limits</h2>
        <ul className="ca-list">
          <li>About {MCP_LIMITS.perMinute} requests a minute and {MCP_LIMITS.perDay.toLocaleString("en-IN")} tool calls a day for each internet address. These are the current defaults and may change.</li>
          <li>Lists are cut when an answer would be very large, and the answer says so. Ask a narrower question to see the rest.</li>
          <li>Company reports are prepared on first request: a company FinLit has not prepared yet answers "being prepared, try again in a few seconds".</li>
        </ul>

        <h2>How fresh the data is</h2>
        <ul className="ca-list">
          <li>Prices and index levels can be delayed and are the last close when the market is shut. The time of each price is in the answer.</li>
          <li>Company figures come from filings, so they are as recent as the latest quarter or year the company has published. Each answer names the period.</li>
          <li>Fund NAVs follow the official AMFI files; institutional flows follow NSDL and exchange reports, which are provisional until confirmed.</li>
          <li>A missing figure is returned as missing (null) with a note. It is never filled with zero or an estimate. Ask the <code>get_data_freshness</code> tool for the newest date of each dataset.</li>
        </ul>

        <p className="ca-note">{MCP_DISCLAIMER} Data may be delayed. Past performance does not indicate future results. See the <Link to="/legal/disclosures">research disclosures</Link>. Questions: <Link to="/contact">contact us</Link>. <Icon name="arrow" /></p>
      </div></section>
    </>
  );
}
