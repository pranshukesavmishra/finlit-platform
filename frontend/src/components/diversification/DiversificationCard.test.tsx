// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import weekly from "./__fixtures__/weekly.json";
import monthly from "./__fixtures__/monthly.json";
import yearly from "./__fixtures__/yearly.json";
import needsThree from "./__fixtures__/needsThree.json";
import * as W from "./wording";

const st = vi.hoisted(() => ({ calls: [] as { path: string; body: Record<string, unknown> }[], fail: 0, gold: true }));
vi.mock("../../lib/api", async (orig) => {
  const m = await orig<typeof import("../../lib/api")>();
  return { ...m, apiSend: vi.fn(async (_method: string, path: string, body: Record<string, unknown>) => {
    st.calls.push({ path, body });
    if (st.fail) throw new m.ApiError(st.fail, { detail: "NIFTY 50 prices are not available right now." });
    const syms = body.symbols as string[];
    if (syms.length < 3) return needsThree;
    const f = (body.horizon === "monthly" ? monthly : body.horizon === "yearly" ? yearly : weekly) as Record<string, unknown>;
    return st.gold ? f : { ...f, styleTilt: { locked: "gold", reason: "The style tilt is built from FinLit Prism ratings, which are part of the Gold plan." } };
  }) };
});
import { DiversificationCard } from "./DiversificationCard";

const SAMPLE = ["RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "TCS", "INFY", "HCLTECH", "ITC", "LT", "BHARTIARTL", "TATASTEEL", "SUNPHARMA"];
const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
beforeEach(() => { st.calls = []; st.fail = 0; st.gold = true; });
afterEach(cleanup);

const FORBIDDEN = /\b(buy(s|ing)?|sell(s|ing)?|hold(s|ing|ings)?|reduc(e|es|ing|tion)|avoid(s|ing)?|accumulat\w*|targets?|best|recommended|consider(s|ing)?|too risky|well diversified|good|poor|weak)\b|your (money|portfolio|exposure)|you (hold|invested|own)/i;

describe("the card shows the sample list as the addendum's sample report does", () => {
  it("headline, parts, sentence, toggle and method line", async () => {
    wrap(<DiversificationCard symbols={SAMPLE} listLabel="Sample list" />);
    await screen.findByText("Fairly spread");
    expect(screen.getByText("These 15 stocks have moved like about 7 independent ones over the last 3 years, and 6 of them are in financial services.")).toBeTruthy();
    expect(screen.getByText(/It measures how spread out the list is, not how safe it is\./)).toBeTruthy();
    expect(screen.getByText("Co-movement")).toBeTruthy(); expect(screen.getByText("Sector spread")).toBeTruthy();
    expect(screen.getByText("Moves like about 7 independent stocks out of 15. TCS, Infosys and HCL Technologies move almost as one.")).toBeTruthy();
    expect(screen.getByText("About 4.4 effective sectors out of 8 that score in full. 6 of the 15 stocks are in financial services.")).toBeTruthy();
    expect(screen.getAllByRole("radio").map((r) => r.textContent)).toEqual(expect.arrayContaining(["Weekly · 3 years", "Monthly · 5 years", "Yearly · indicative"]));
    expect(screen.getByText("Weekly prices, Nov 2023 – Oct 2026. Describes how these stocks have moved together in the past; it is information, not a recommendation, and these relationships can change.")).toBeTruthy();
    expect(screen.getByText("Size: 15 large caps · 0 mid · 0 small")).toBeTruthy();
    expect(screen.getByText("Business groups: Tata 2 (TCS, Tata Steel)")).toBeTruthy();
    expect(screen.getByText("Over the last year these stocks have moved like about 7 independent ones, the same as over 3 years. No pair's correlation has changed by 0.30 or more.")).toBeTruthy();
    expect(screen.getByText("If equal amounts were held, Information technology would be 20.0% of the amount but 23.7% of the risk.")).toBeTruthy();
    expect(screen.getByText(/53rd percentile/)).toBeTruthy(); expect(screen.getByText(/61st percentile/)).toBeTruthy(); expect(screen.getByText(/82nd percentile/)).toBeTruthy();
    expect(screen.getByText(/72nd percentile/)).toBeTruthy(); expect(screen.getByText(/48th percentile/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/\d+th percentile.*\b(53|61|72|82)th/);
    expect(screen.getByText("This list leans towards lower-risk and higher-quality companies, and stocks in short-term uptrends. Growth & profitability, valuation and the long-term trend are close to typical.")).toBeTruthy();
    expect(st.calls.every((c) => Object.keys(c.body).sort().join() === "benchmark,horizon,symbols")).toBe(true);   // names only go out
  });

  it("the horizon toggle changes the co-movement figures and never the score", async () => {
    wrap(<DiversificationCard symbols={SAMPLE} />);
    await screen.findByText("Fairly spread");
    fireEvent.click(screen.getByRole("radio", { name: "Monthly · 5 years" }));
    await screen.findByText("On monthly returns over 5 years, these stocks have moved like about 6 independent ones.");
    expect(screen.getAllByText("0.28").length).toBeGreaterThan(0); expect(screen.getByText("0.91")).toBeTruthy(); expect(screen.getByText(/59 monthly returns/)).toBeTruthy();
    expect(screen.getByText("Fairly spread")).toBeTruthy(); expect(screen.getAllByText("72").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("radio", { name: "Yearly · indicative" }));
    await screen.findByText(/Indicative: about 7 years of data/);
    expect(screen.getAllByText("0.49").length).toBeGreaterThan(0); expect(screen.queryByText("Groups that move together")).toBeNull(); expect(screen.getByText("Most and least related pairs")).toBeTruthy();
    expect(screen.getAllByText("72").length).toBeGreaterThan(0);
  });

  it("the risk view switches between equal amounts and company value, and between sector and stock", async () => {
    wrap(<DiversificationCard symbols={SAMPLE} />);
    await screen.findByText("Fairly spread");
    fireEvent.click(screen.getByRole("radio", { name: "If sized by company value" }));
    expect(screen.getByText(/If sized by company value, /)).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "By stock" }));
    expect(screen.getByText(/Reliance Industries would be 16\.2% of the amount and 19\.1% of the risk/)).toBeTruthy();
  });
});

describe("honest states", () => {
  it("fewer than 3 stocks: no score, the note, and the spread by count", async () => {
    wrap(<DiversificationCard symbols={["TCS", "INFY"]} />);
    await screen.findByText(/The score needs at least 3 stocks with a year of prices/);
    expect(screen.queryByText("Diversification score")).toBeNull(); expect(screen.getByText("Spread by count")).toBeTruthy();
  });
  it("a failed request says why and offers to try again", async () => {
    st.fail = 502;
    wrap(<DiversificationCard symbols={SAMPLE} />);
    await screen.findByText("The diversification figures could not be worked out.", {}, { timeout: 5000 });
    expect(screen.getByText("NIFTY 50 prices are not available right now.")).toBeTruthy(); expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
  it("a plan without Prism sees why the style tilt is blank", async () => {
    st.gold = false;
    wrap(<DiversificationCard symbols={SAMPLE} />);
    await screen.findByText(/which are part of the Gold plan/);
  });
  it("an empty list asks for a name instead of calling the service", async () => {
    wrap(<DiversificationCard symbols={[]} />);
    expect(screen.getByText("No names in this list.")).toBeTruthy(); expect(st.calls.length).toBe(0);
  });
});

describe("what-if: the person's own choices only", () => {
  it("leaving a name out asks again with that name missing; adding sends the chosen name; the site proposes nothing", async () => {
    wrap(<DiversificationCard symbols={SAMPLE} candidates={[["WIPRO", "Wipro"], ["ITC", "ITC"]]} />);
    await screen.findByText("Fairly spread");
    fireEvent.click(screen.getByText("Try a different list"));
    fireEvent.click(screen.getByRole("button", { name: /^TCS/ }));
    await waitFor(() => expect(st.calls.some((c) => !(c.body.symbols as string[]).includes("TCS"))).toBe(true));
    fireEvent.change(screen.getByLabelText("Add a name to the list"), { target: { value: "WIPRO" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(st.calls.some((c) => (c.body.symbols as string[]).includes("WIPRO"))).toBe(true));
    expect(document.querySelector("datalist")!.querySelectorAll("option").length).toBe(2);       // only the search list the page gave it
    expect(screen.getByText(/FinLit does not suggest names/)).toBeTruthy();
  });
});

describe("wording: the card describes and never advises", () => {
  it("no sentence the card can show contains a word from the Never use list", async () => {
    const { container } = wrap(<DiversificationCard symbols={SAMPLE} candidates={[["WIPRO", "Wipro"]]} />);
    await screen.findByText("Fairly spread");
    fireEvent.click(screen.getByText("Try a different list"));
    for (const h of ["monthly", "yearly", "weekly"]) { fireEvent.click(screen.getByRole("radio", { name: new RegExp(h, "i") })); await waitFor(() => expect(container.textContent).toMatch(/Correlations from/)); }
    fireEvent.click(screen.getByRole("radio", { name: "If sized by company value" })); fireEvent.click(screen.getByRole("radio", { name: "By stock" }));
    const text = (container.textContent || "").replace(/([a-z.%)])([A-Z])/g, "$1 $2");
    expect(text).not.toMatch(FORBIDDEN);
    const strings = [W.SIDE_NOTE, W.NOT_SAFETY, W.SCORE_FORMULA, W.NEEDS_THREE, W.NEEDS_THREE_NOTE, W.SCORE_ALWAYS_WEEKLY, W.clusterIntro, W.clusterIntroFor("monthly"), W.methodLine({ label: "Nov 2023 – Oct 2026", frequency: "weekly" }),
      W.methodLine({ label: "x", frequency: "monthly" }, "monthly"), W.methodLine({ label: "x", frequency: "yearly" }, "yearly"), W.tiltFoot(650), W.summaryText(weekly as never, "weekly"), W.summaryText(needsThree as never, "weekly"),
      W.recentSentence(weekly as never), W.recentFoot(weekly as never), W.spreadSentence(weekly as never), W.groupLine(weekly as never), W.sizeLine(weekly as never), W.otherStocks(weekly as never), W.eachStockFoot(weekly as never),
      W.riskSentence(weekly as never, "equal", "sector"), W.riskSentence(weekly as never, "mcap", "stock"), W.notRatedNote(["A", "B"]), W.unclassifiedNote({ spread: { unclassified: ["A"] } } as never),
      ...W.excludedNotes({ names: {}, excluded: [{ symbol: "A", reason: "history", weeks: 30 }, { symbol: "B", reason: "noPrices" }, { symbol: "C", reason: "unknown" }, { symbol: "D", reason: "overlap" }] } as never),
      ...(weekly as never as { styleTilt: { parts: never[] } }).styleTilt.parts.map((p) => W.tiltRead(p)), ...W.HORIZONS.map((h) => h.label), ...W.BANDS.map((b) => b.label)];
    for (const s of strings) expect(s, s).not.toMatch(FORBIDDEN);
  });
  it("ordinals are right (53rd, 61st, 82nd, 72nd, 48th, 11th, 12th, 13th, 21st, 101st)", () => {
    expect([53, 61, 82, 72, 48, 65, 11, 12, 13, 21, 101, 112].map(W.ordinal)).toEqual(["53rd", "61st", "82nd", "72nd", "48th", "65th", "11th", "12th", "13th", "21st", "101st", "112th"]);
  });
  it("no green or red colour is used anywhere in the card's stylesheet", async () => {
    const css = (await import("node:fs")).readFileSync("src/components/diversification/diversification.css", "utf8");
    expect(css).not.toMatch(/financial-(positive|negative)|\bgreen\b|\bred\b|#(?:16|4A|B9|FC)[0-9A-F]{4}\b|--band-(hi|lo|mid)/i);
  });
  it("an unrated stock is named in a note", () => { expect(W.notRatedNote(["XYZ"])).toBe("1 stock is not rated by Prism yet (XYZ), so it is left out of the style tilt only."); void within; });
});
