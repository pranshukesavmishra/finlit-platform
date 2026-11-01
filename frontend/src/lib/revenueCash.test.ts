import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { BASE, GROUPS, buildYears, fmtCr, fmtPct, industryGroup, isLenderLike, revenueCash, type RevenueCash, type RuleId } from "./revenueCash";

type Rows = Record<string, (number | null)[]>;
const t = (periods: string[], rows: Rows) => ({ unit: "Cr", period: "yearly", periods, periodEnds: periods, rows });
const P = ["FY20", "FY21", "FY22", "FY23", "FY24", "FY25", "FY26"];

/** A steady, healthy company by default; each test overrides what it needs. */
function co(o: { rev?: (number | null)[]; ocf?: (number | null)[]; np?: (number | null)[]; fcf?: (number | null)[]; capex?: (number | null)[]; rec?: (number | null)[]; inv?: (number | null)[]; fa?: (number | null)[]; periods?: string[] } = {}) {
  const per = o.periods ?? P, n = per.length;
  const rev = o.rev ?? Array.from({ length: n }, (_, i) => 1000 * 1.1 ** i);
  const pick = (v: (number | null)[] | undefined, f: (i: number) => number | null) => v ?? Array.from({ length: n }, (_, i) => f(i));
  return {
    pl: t(per, { revenue: rev, net_profit: pick(o.np, (i) => (rev[i] == null ? null : (rev[i] as number) * 0.08)) }),
    bs: t(per, { receivables: pick(o.rec, (i) => 100 * 1.1 ** i), inventories: pick(o.inv, (i) => 80 * 1.1 ** i), fixed_assets: pick(o.fa, (i) => 500 * 1.05 ** i), cwip: pick(undefined, () => 20) }),
    cf: t(per, { operating: pick(o.ocf, (i) => (rev[i] == null ? null : (rev[i] as number) * 0.12)), capex: pick(o.capex, (i) => (rev[i] == null ? null : -(rev[i] as number) * 0.04)), free_cash_flow: pick(o.fcf, (i) => (rev[i] == null ? null : (rev[i] as number) * 0.08)) }),
  };
}
const run = (o: Parameters<typeof co>[0] = {}, opts: { lender?: boolean; labels?: string[] } = {}): RevenueCash => {
  const d = co(o);
  return revenueCash(d.pl, d.bs, d.cf, { lender: !!opts.lender, labels: opts.labels });
};
const ids = (r: RevenueCash) => r.warnings.map((w) => w.id);
const w = (r: RevenueCash, id: RuleId) => r.warnings.find((x) => x.id === id);
/** Revenue 1000 -> 1579 (+57.9%) with the latest operating cash flow at -101 (-6.4%): the spec's example company. */
const mock = (extra: Parameters<typeof co>[0] = {}) => run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1579], ocf: [80, 80, 80, 80, 80, 80, -101], ...extra });

describe("formatting: minus sign, rounding, no negative zero", () => {
  it("uses U+2212 and the site's grouping", () => {
    expect(fmtPct(-6.44)).toBe("−6.4%");
    expect(fmtPct(57.94, 1, true)).toBe("+57.9%");
    expect(fmtPct(102.3, 1, true)).toBe("+102.3%");
    expect(fmtPct(1234.5, 1)).toBe("1,234.5%");
    expect(fmtCr(-312.4)).toBe("−₹312 crore");
    expect(fmtCr(123456.7)).toBe("₹1,23,457 crore");
  });
  it("a value that rounds to zero carries no sign", () => {
    expect(fmtPct(-0.04)).toBe("0.0%");
    expect(fmtPct(0.04, 1, true)).toBe("0.0%");
    expect(fmtCr(-0.04)).toBe("₹0.0 crore");
    expect(fmtPct(null)).toBe("n/a");
  });
});

describe("indicator maths", () => {
  it("reproduces the example figures: growth +57.9%, OCF margin −6.4%", () => {
    const r = run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1579], ocf: [80, 80, 80, 80, 80, 80, -101] });
    expect(r.latest!.revenueGrowth).toBe(57.9);
    expect(r.latest!.ocfMargin).toBe(-6.4);
    expect(r.status).toBe("Needs attention");
  });
  it("receivables +89% on year-end balances when only two year-ends exist; gap 31.1 points", () => {
    const r = run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1579], rec: [null, null, null, null, null, 100, 189] });
    expect(r.latest!.receivablesGrowth).toBe(89);
    expect(r.latest!.receivablesBasis).toBe("year-end");
    expect(r.latest!.receivablesGap).toBe(31.1);
    expect(w(r, "receivables")!.why).toBe("Receivables grew 89.0%, exceeding revenue growth (57.9%) by 31.1 percentage points.");
    expect(w(r, "receivables")!.note).toMatch(/year-end/);
  });
  it("uses average balances when three year-ends exist", () => {
    const r = run({ rec: [null, null, null, null, 100, 120, 180] });   // averages 110 -> 150
    expect(r.latest!.receivablesBasis).toBe("average");
    expect(r.latest!.receivablesGrowth).toBe(36.4);
  });
  it("growth is not worked out from a zero or missing earlier year", () => {
    const r = run({ inv: [null, null, null, null, null, 0, 50] });
    expect(r.latest!.inventoryGrowth).toBeNull();
    expect(r.latest!.inventoryBasis).toBeNull();
  });
  it("revenue of zero gives no margin and no growth, never infinity", () => {
    const r = run({ rev: [1000, 1000, 1000, 1000, 1000, 0, 500] });
    expect(r.years.at(-2)!.ocfMargin).toBeNull();
    expect(r.latest!.revenueGrowth).toBeNull();
  });
  it("a missing year is a gap (null), never zero", () => {
    const r = run({ ocf: [100, 100, 100, null, 100, 100, 100], rev: [1000, 1000, 1000, 1000, 1000, 1000, 1000] });
    const y = r.years.find((x) => x.period === "FY23")!;
    expect(y.ocf).toBeNull(); expect(y.ocfMargin).toBeNull();
    expect(r.years).toHaveLength(5);
  });
});

describe("Rule 1: OCF margin below 0% -> Critical", () => {
  it("triggers on a negative margin", () => {
    const r = mock();
    const x = w(r, "ocf_negative")!;
    expect(x.text).toBe("Revenue is not generating positive operating cash"); expect(x.severity).toBe("Critical");
    expect(x.why).toBe("FY26 operating cash flow was −₹101 crore on revenue of ₹1,579 crore, an OCF margin of −6.4%.");
    expect(x.pattern).toBe("This year only");
  });
  it("does not trigger at exactly 0% or when the margin rounds to 0.0%", () => {
    expect(ids(run({ ocf: [100, 100, 100, 100, 100, 100, 0] }))).not.toContain("ocf_negative");
    expect(ids(run({ rev: Array(7).fill(1000), ocf: [100, 100, 100, 100, 100, 100, -0.4] }))).not.toContain("ocf_negative");
    expect(ids(run({ rev: Array(7).fill(1000), ocf: [100, 100, 100, 100, 100, 100, -0.6] }))).toContain("ocf_negative");
  });
  it("is a persistent problem when it repeats", () => {
    const r = run({ rev: Array(7).fill(1000), ocf: [100, 100, -10, -20, -30, 50, -40] });
    expect(w(r, "ocf_negative")!.pattern).toBe("4 of the last 5 years");
  });
  it("does not trigger when operating cash flow is missing", () => {
    const r = run({ ocf: [100, 100, 100, 100, 100, 100, null] });
    expect(ids(r)).not.toContain("ocf_negative"); expect(r.latest!.ocfMargin).toBeNull(); expect(r.status).toBeNull();
  });
});

describe("Rule 2: OCF margin below 5% for 3 years -> High", () => {
  const rev = Array(7).fill(1000);
  const margin = (a: number, b: number, c: number) => run({ rev, ocf: [100, 100, 100, 100, a * 10, b * 10, c * 10] });
  it("triggers when all of the last three years are below 5%", () => {
    const r = margin(3, 4, 2);
    expect(w(r, "weak_consistency")!.severity).toBe("High"); expect(w(r, "weak_consistency")!.text).toBe("Weak cash conversion consistency");
    expect(w(r, "weak_consistency")!.why).toBe("OCF margin was under 5% in each of the last 3 years: FY24 3.0%, FY25 4.0%, FY26 2.0%.");
  });
  it("boundary: exactly 5.0% is not below", () => { expect(ids(margin(5, 3, 3))).not.toContain("weak_consistency"); expect(ids(margin(4.9, 3, 3))).toContain("weak_consistency"); });
  it("judged on the displayed figure: 4.96% reads 5.0% and does not trigger", () => { expect(ids(margin(4.96, 3, 3))).not.toContain("weak_consistency"); });
  it("two weak years are not enough", () => { expect(ids(margin(8, 3, 3))).not.toContain("weak_consistency"); });
  it("a missing year in the window blocks it (no guessing)", () => {
    const r = run({ rev, ocf: [100, 100, 100, 100, null, 30, 30] });
    expect(ids(r)).not.toContain("weak_consistency");
  });
  it("needs three years of data", () => {
    const d = co({ periods: ["FY25", "FY26"] });
    const r = revenueCash(d.pl, d.bs, t(["FY25", "FY26"], { operating: [10, 10], free_cash_flow: [1, 1], capex: [-1, -1] }), { lender: false });
    expect(ids(r)).not.toContain("weak_consistency");
    expect(r.notEvaluated.join(" ")).toMatch(/three years/);
  });
});

describe("Rule 3: revenue growth positive and OCF negative -> Critical", () => {
  it("triggers", () => { const x = w(mock(), "sales_not_cash")!; expect(x.severity).toBe("Critical"); expect(x.text).toBe("Sales growth is not translating into cash"); expect(x.why).toBe("Revenue grew 57.9% in FY26 while operating cash flow was −₹101 crore."); expect(x.investigate).toBe("working capital requirements and customer collections"); });
  it("not when revenue is flat or falling", () => {
    expect(ids(run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1000], ocf: [1, 1, 1, 1, 1, 1, -50] }))).not.toContain("sales_not_cash");
    expect(ids(run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 900], ocf: [1, 1, 1, 1, 1, 1, -50] }))).not.toContain("sales_not_cash");
  });
  it("not when operating cash flow is positive", () => { expect(ids(run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1500], ocf: [1, 1, 1, 1, 1, 1, 5] }))).not.toContain("sales_not_cash"); });
});

describe("Rules 4 and 5: receivables / inventory growth exceeds revenue growth by more than 20 points -> High", () => {
  const base = { rev: [1000, 1000, 1000, 1000, 1000, 1000, 1500] };   // revenue +50.0%
  it("triggers above 20 points", () => {
    const r = run({ ...base, rec: [null, null, null, null, null, 100, 171], inv: [null, null, null, null, null, 100, 171] });   // +71.0% = 21.0 points
    expect(w(r, "receivables")!.severity).toBe("High"); expect(w(r, "receivables")!.text).toBe("Customer collection risk");
    expect(w(r, "inventory")!.severity).toBe("High"); expect(w(r, "inventory")!.text).toBe("Inventory accumulation risk");
    expect(w(r, "inventory")!.why).toBe("Inventory grew 71.0%, exceeding revenue growth (50.0%) by 21.0 percentage points.");
  });
  it("boundary: exactly 20.0 points does not trigger; 20.1 does", () => {
    const at20 = run({ ...base, rec: [null, null, null, null, null, 100, 170], inv: [null, null, null, null, null, 100, 170] });
    expect(at20.latest!.receivablesGap).toBe(20); expect(ids(at20)).not.toContain("receivables"); expect(ids(at20)).not.toContain("inventory");
    const over = run({ ...base, rec: [null, null, null, null, null, 1000, 1701], inv: [null, null, null, null, null, 1000, 1701] });   // +70.1%
    expect(over.latest!.receivablesGap).toBe(20.1); expect(ids(over)).toContain("receivables"); expect(ids(over)).toContain("inventory");
  });
  it("is silent when the balance is not reported", () => { const r = run({ ...base, rec: Array(7).fill(null), inv: Array(7).fill(null) }); expect(ids(r)).not.toContain("receivables"); expect(r.latest!.receivablesGrowth).toBeNull(); });
  it("reports the persistent pattern", () => {
    const r = run({ rev: Array(7).fill(1000), rec: [100, 100, 100, 200, 400, 800, 1600] });
    expect(w(r, "receivables")!.pattern).toBe("4 of the last 5 years");
  });
});

describe("Rule 6: debtor days increase over 20% -> High", () => {
  const flat = { rev: Array(7).fill(1000) };
  it("boundary: exactly +20% does not trigger; just over does", () => {
    expect(ids(run({ ...flat, rec: [null, null, null, null, null, 100, 120] }))).not.toContain("debtor_days");
    const r = run({ ...flat, rec: [null, null, null, null, null, 100, 121] });
    expect(ids(r)).toContain("debtor_days"); expect(w(r, "debtor_days")!.text).toBe("Collection efficiency deteriorating");
    expect(w(r, "debtor_days")!.why).toBe("Debtor days rose from about 37 to 44 days in FY26 (+21.0%).");
  });
  it("is compared on one basis for both years", () => {
    const r = run({ ...flat, rec: [null, null, null, null, 100, 100, 160] });   // averages 100 -> 130: +30%
    expect(r.latest!.debtorDaysChange).toBe(30);
  });
  it("needs revenue in both years", () => { expect(ids(run({ rev: [1000, 1000, 1000, 1000, 1000, null, 1000], rec: [null, null, null, null, null, 100, 300] }))).not.toContain("debtor_days"); });
});

describe("Rule 7: free cash flow negative for 3 consecutive years -> High", () => {
  const neg = (n: number, extra: Parameters<typeof co>[0] = {}) => run({ rev: Array(7).fill(1000), fcf: [50, 50, 50, 50, ...Array(3).fill(-20).map((v, i) => (i < n ? v : 20)).reverse().slice(0)].slice(0, 7), ...extra });
  it("triggers on three negative years", () => { const r = run({ rev: Array(7).fill(1000), fcf: [50, 50, 50, 50, -10, -20, -30] }); const x = w(r, "fcf_negative")!; expect(x.severity).toBe("High"); expect(x.text).toBe("Expansion may require external funding"); expect(x.why).toBe("Free cash flow was negative in each of the last 3 years: FY24 −₹10 crore, FY25 −₹20 crore, FY26 −₹30 crore."); });
  it("not on two negative years or a zero", () => {
    expect(ids(run({ rev: Array(7).fill(1000), fcf: [50, 50, 50, 50, 10, -20, -30] }))).not.toContain("fcf_negative");
    expect(ids(run({ rev: Array(7).fill(1000), fcf: [50, 50, 50, 50, -10, 0, -30] }))).not.toContain("fcf_negative");
    void neg;
  });
  it("a missing year breaks the run", () => { expect(ids(run({ rev: Array(7).fill(1000), fcf: [50, 50, 50, 50, -10, null, -30], ocf: Array(7).fill(null), capex: Array(7).fill(null) }))).not.toContain("fcf_negative"); });
  it("falls back to operating cash flow plus capex when free cash flow is not reported", () => {
    const r = run({ rev: Array(7).fill(1000), fcf: Array(7).fill(null), ocf: [100, 100, 100, 100, 20, 20, 20], capex: [-10, -10, -10, -10, -50, -50, -50] });
    expect(ids(r)).toContain("fcf_negative");
  });
  it("planned expansion (capex 10%+ of revenue, fixed assets up 10%+, revenue growing) lowers it to Moderate and says so", () => {
    const rev = [1000, 1000, 1000, 1000, 1000, 1000, 1200];
    const r = run({ rev, fcf: [50, 50, 50, 50, -10, -20, -30], capex: [-40, -40, -40, -40, -100, -100, -150], fa: [500, 500, 500, 500, 500, 600, 800] });
    const x = w(r, "fcf_negative")!;
    expect(x.severity).toBe("Moderate"); expect(x.baseSeverity).toBe("High");
    expect(x.note).toMatch(/lower: capital spending was 12\.5% of revenue, fixed assets and work in progress rose 32\.3% and revenue grew 20\.0% in FY26/);
  });
  it("is not downgraded when capex is low, assets are flat, or revenue is not growing", () => {
    const f = [50, 50, 50, 50, -10, -20, -30];
    expect(w(run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1200], fcf: f, capex: Array(7).fill(-50), fa: [500, 500, 500, 500, 500, 600, 800] }), "fcf_negative")!.severity).toBe("High");
    expect(w(run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1200], fcf: f, capex: Array(7).fill(-150), fa: Array(7).fill(500) }), "fcf_negative")!.severity).toBe("High");
    expect(w(run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 900], fcf: f, capex: Array(7).fill(-150), fa: [500, 500, 500, 500, 500, 600, 800] }), "fcf_negative")!.severity).toBe("High");
  });
  it("a capital-intensive business is shown one level lower, once (not twice)", () => {
    const r = run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1200], fcf: [50, 50, 50, 50, -10, -20, -30], capex: [-40, -40, -40, -40, -100, -100, -150], fa: [500, 500, 500, 500, 500, 600, 800] }, { labels: ["Utilities", "Power generation"] });
    expect(w(r, "fcf_negative")!.severity).toBe("Moderate");
    const flat = run({ rev: Array(7).fill(1000), fcf: [50, 50, 50, 50, -10, -20, -30] }, { labels: ["Utilities", "Power generation"] });
    expect(w(flat, "fcf_negative")!.severity).toBe("Moderate"); expect(flat.caveat).toMatch(/Capital-intensive/);
  });
  it("does not lower the operating cash flow rules: capex sits outside operating cash flow", () => {
    const r = mock({ capex: [-40, -40, -40, -40, -40, -40, -300], fa: [500, 500, 500, 500, 500, 500, 900] });
    expect(w(r, "ocf_negative")!.severity).toBe("Critical");
  });
});

describe("Rule 8: five-year OCF below five-year net profit -> High", () => {
  it("triggers", () => {
    const r = run({ rev: Array(7).fill(1000), np: Array(7).fill(100), ocf: [100, 100, 80, 80, 80, 80, 80] });
    expect(w(r, "cum_ocf_profit")!.text).toBe("Earnings have weak cash backing"); expect(w(r, "cum_ocf_profit")!.severity).toBe("High");
    expect(w(r, "cum_ocf_profit")!.why).toBe("Over FY22 to FY26 operating cash flow totalled ₹400 crore against net profit of ₹500 crore, 80% of profit."); expect(w(r, "cum_ocf_profit")!.pattern).toBe("5-year view");
  });
  it("boundary: equal totals do not trigger", () => { expect(ids(run({ rev: Array(7).fill(1000), np: Array(7).fill(100), ocf: [1, 1, 100, 100, 100, 100, 100] }))).not.toContain("cum_ocf_profit"); });
  it("needs five years of both figures", () => {
    const r = run({ rev: Array(7).fill(1000), np: Array(7).fill(100), ocf: [1, 1, null, 10, 10, 10, 10] });
    expect(ids(r)).not.toContain("cum_ocf_profit"); expect(r.notEvaluated.join(" ")).toMatch(/five years/);
    const short = run({ periods: ["FY23", "FY24", "FY25", "FY26"], np: [100, 100, 100, 100], ocf: [1, 1, 1, 1] });
    expect(ids(short)).not.toContain("cum_ocf_profit");
  });
  it("is not worked out when five-year profit is not positive", () => { expect(ids(run({ rev: Array(7).fill(1000), np: Array(7).fill(-10), ocf: Array(7).fill(-50) }))).not.toContain("cum_ocf_profit"); });
});

describe("Rule 9: OCF margin improves for 3 consecutive years -> Positive", () => {
  const rev = Array(7).fill(1000);
  const m = (...v: number[]) => run({ rev, ocf: [100, 100, 100, ...v.map((x) => x * 10)] });
  it("triggers on three rises in a row", () => {
    const r = m(1, 2, 3, 4);
    expect(w(r, "improving")!.text).toBe("Cash conversion improving"); expect(w(r, "improving")!.severity).toBe("Positive"); expect(w(r, "improving")!.investigate).toBeNull();
    expect(w(r, "improving")!.why).toBe("OCF margin rose in each of the last 3 years: FY23 1.0% → FY24 2.0% → FY25 3.0% → FY26 4.0%.");
    expect(r.status).toBe("Improving");
  });
  it("not with a flat step, a dip, or only two rises", () => { expect(ids(m(1, 2, 2, 4))).not.toContain("improving"); expect(ids(m(1, 3, 2, 4))).not.toContain("improving"); expect(ids(m(5, 1, 2, 3))).not.toContain("improving"); });
  it("at or above 5% the headline stays Healthy", () => { const r = m(5, 6, 7, 8); expect(ids(r)).toContain("improving"); expect(r.status).toBe("Healthy"); });
  it("a missing year breaks the run", () => { expect(ids(run({ rev, ocf: [100, 100, 100, 10, null, 30, 40] }))).not.toContain("improving"); });
});

describe("headline status", () => {
  it("Needs attention / Watch / Healthy at the 0% and 5% lines", () => {
    const at = (v: number) => run({ rev: Array(7).fill(1000), ocf: [100, 100, 100, 100, 100, 100, v * 10] }).status;
    expect(at(-0.1)).toBe("Needs attention"); expect(at(0)).toBe("Watch"); expect(at(4.9)).toBe("Watch"); expect(at(5)).toBe("Healthy");
  });
});

describe("single severe event versus persistent problem", () => {
  it("labels a one-year dip 'This year only' and a repeat '3 of the last 5 years'", () => {
    expect(w(run({ rev: Array(7).fill(1000), ocf: [100, 100, 100, 100, 100, 100, -50] }), "ocf_negative")!.pattern).toBe("This year only");
    expect(w(run({ rev: Array(7).fill(1000), ocf: [100, 100, 100, -5, 100, -10, -50] }), "ocf_negative")!.pattern).toBe("3 of the last 5 years");
  });
  it("says how little data there is when fewer than three years can be judged", () => {
    const d = co({ periods: ["FY25", "FY26"], rev: [1000, 1000] });
    const r = revenueCash(d.pl, d.bs, t(["FY25", "FY26"], { operating: [50, -50] }), { lender: false });
    expect(w(r, "ocf_negative")!.pattern).toBe("Based on only 2 years of data");
  });
});

describe("annual is compared with annual: quarterly or trailing figures are never read", () => {
  it("the engine takes only the yearly tables and its source never touches quarterly data", () => {
    const src = readFileSync(__dirname + "/revenueCash.ts", "utf8").replace(/\/\*[\s\S]*?\*\//, "").split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
    expect(src).not.toMatch(/quarter|ttm/i);
    expect(revenueCash.length).toBe(4);
  });
  it("buildYears reads the periods it is given and nothing else", () => { expect(buildYears(co().pl, co().bs, co().cf).map((y) => y.period)).toEqual(P.slice(-8)); });
});

describe("lenders", () => {
  it("returns the 'not comparable' state with no figures", () => {
    const r = run({}, { lender: true });
    expect(r.state).toBe("lender"); expect(r.years).toEqual([]); expect(r.warnings).toEqual([]); expect(r.status).toBeNull(); expect(r.notes[0]).toMatch(/bank, NBFC or insurer/);
  });
  it("detects lenders by the site's isBank flag, and insurers by name", () => {
    expect(isLenderLike(true)).toBe(true); expect(isLenderLike(false, "Financial Services", "Life Insurance")).toBe(true);
    expect(isLenderLike(false, "Banks", null)).toBe(true); expect(isLenderLike(false, "Information Technology", "Software")).toBe(false);
  });
});

describe("industry groups: softened thresholds, a caveat and a lower level", () => {
  it("classifies from sector, industry and sub-industry", () => {
    expect(industryGroup("Industrials", "Construction & Engineering")).toBe("project");
    expect(industryGroup("Consumer Staples", "Sugar")).toBe("seasonal");
    expect(industryGroup("Consumer Discretionary", "Jewellery Retail")).toBe("trading");
    expect(industryGroup("Utilities", "Power")).toBe("capital");
    expect(industryGroup("Information Technology", "IT Services")).toBe("standard");
    expect(industryGroup(null, undefined)).toBe("standard");
  });
  it("a 25-point gap triggers for a general company and not for an EPC company", () => {
    const o = { rev: [1000, 1000, 1000, 1000, 1000, 1000, 1500], rec: [null, null, null, null, null, 100, 175] as (number | null)[] };   // +75% vs +50%
    expect(ids(run(o))).toContain("receivables");
    const epc = run(o, { labels: ["Industrials", "Construction"] });
    expect(ids(epc)).not.toContain("receivables"); expect(epc.caveat).toMatch(/Project and EPC/);
    const big = run({ ...o, rec: [null, null, null, null, null, 100, 190] }, { labels: ["Industrials", "Construction"] });   // 40 points
    expect(w(big, "receivables")!.severity).toBe("Moderate"); expect(w(big, "receivables")!.note).toMatch(/one level lower/);
  });
  it("trading: the weak-margin line drops to 2%", () => {
    const o = { rev: Array(7).fill(1000), ocf: [100, 100, 100, 100, 30, 30, 30] };
    expect(ids(run(o))).toContain("weak_consistency");
    expect(ids(run(o, { labels: ["Retail", "Trading"] }))).not.toContain("weak_consistency");
    expect(ids(run({ ...o, ocf: [100, 100, 100, 100, 10, 10, 10] }, { labels: ["Retail", "Trading"] }))).toContain("weak_consistency");
  });
  it("the negative-OCF rules are never softened by a group", () => {
    for (const labels of [["Construction"], ["Sugar"], ["Trading"], ["Power"]]) { const r = mock({}); void r; expect(w(run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1579], ocf: [80, 80, 80, 80, 80, 80, -101] }, { labels }), "ocf_negative")!.severity).toBe("Critical"); }
  });
  it("states that no industry benchmark is available instead of inventing one", () => { expect(run().benchmark).toBe("Industry benchmark not available"); });
  it("every adjusted group documents a caveat", () => { for (const [k, g] of Object.entries(GROUPS)) if (k !== "standard") expect(g.adjust.caveat, k).toBeTruthy(); expect(BASE.gapPp).toBe(20); expect(BASE.weakOcfMargin).toBe(5); });
});

describe("generated sentences", () => {
  it("reads like the example for the spec's company", () => {
    const r = mock({ rec: [null, null, null, null, null, 100, 189], inv: [null, null, null, null, null, 100, 202.3] });
    expect(r.reading).toContain("Revenue expansion is strong, but cash conversion is weak.");
    expect(r.reading).toContain("Rising receivables and inventory may be contributing to working capital pressure.");
    expect(r.next).toBe("Debtor days, inventory days, operating cash flow trend and cash flow from operations over the last five years.");
  });
  it("says so when nothing triggers", () => { const r = run(); expect(r.warnings).toEqual([]); expect(r.reading).toMatch(/None of the rules/); expect(r.status).toBe("Healthy"); });
  it("does not call a falling balance 'rising'", () => {
    const r = run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 500], rec: [null, null, null, null, null, 100, 95], inv: Array(7).fill(null) });
    expect(w(r, "receivables")).toBeDefined(); expect(r.reading).toMatch(/Receivables growing faster than revenue/); expect(r.reading).not.toMatch(/Rising receivables/);
  });
});

describe("wording: descriptive, never advice, never an accusation", () => {
  const FORBIDDEN = /\b(buy|sell|hold|avoid|recommend\w*|should|must|ought|advis\w*|accumulate|exit|target price|fraud\w*|manipulat\w*|cook\w*|fake\w*|scam\w*|cheat\w*|dishonest\w*|window.?dressing|siphon\w*)\b/i;
  it("no warning, reading, next step, caveat or note uses such a word", () => {
    const scenarios: RevenueCash[] = [
      mock({ rec: [null, null, null, null, null, 100, 189], inv: [null, null, null, null, null, 100, 202.3] }),
      run({ rev: Array(7).fill(1000), np: Array(7).fill(100), ocf: [100, 100, 80, 80, 80, 80, 80], fcf: [50, 50, 50, 50, -10, -20, -30], rec: [null, null, null, null, 100, 100, 160] }),
      run({ rev: Array(7).fill(1000), ocf: [100, 100, 100, 10, 20, 30, 40] }),
      run(), run({}, { lender: true }),
      ...(["Construction", "Sugar", "Trading", "Power"].map((l) => mock({ rec: [null, null, null, null, null, 100, 300] }) && run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1500], rec: [null, null, null, null, null, 100, 300], fcf: [50, 50, 50, 50, -10, -20, -30], ocf: [100, 100, 100, 10, 20, 30, 40] }, { labels: [l] }))),
    ];
    const text = [
      ...Object.values(GROUPS).map((g) => g.adjust.caveat ?? ""),
      ...scenarios.flatMap((r) => [r.reading, r.next, r.statusLine, r.caveat ?? "", r.benchmark, ...r.notes, ...r.notEvaluated, ...r.warnings.flatMap((x) => [x.text, x.why, x.investigate ?? "", x.note ?? "", x.pattern])]),
    ].filter(Boolean);
    expect(text.length).toBeGreaterThan(30);
    for (const s of text) expect(s, s).not.toMatch(FORBIDDEN);
  });
  it("uses exactly the rule texts and severities of the spec", () => {
    const spec: Record<RuleId, [string, string]> = {
      ocf_negative: ["Revenue is not generating positive operating cash", "Critical"], weak_consistency: ["Weak cash conversion consistency", "High"], sales_not_cash: ["Sales growth is not translating into cash", "Critical"],
      receivables: ["Customer collection risk", "High"], inventory: ["Inventory accumulation risk", "High"], debtor_days: ["Collection efficiency deteriorating", "High"],
      fcf_negative: ["Expansion may require external funding", "High"], cum_ocf_profit: ["Earnings have weak cash backing", "High"], improving: ["Cash conversion improving", "Positive"],
    };
    const r = run({ rev: [1000, 1000, 1000, 1000, 1000, 1000, 1500], np: Array(7).fill(100), ocf: [100, 100, 100, 10, 20, 30, 40], fcf: [50, 50, 50, 50, -10, -20, -30], rec: [null, null, null, null, 100, 100, 300], inv: [null, null, null, null, null, 100, 300] });
    const r2 = mock();
    const m = (...v: number[]) => run({ rev: Array(7).fill(1000), ocf: [100, 100, 100, ...v.map((x) => x * 10)] });
    const up = m(1, 2, 3, 4);
    const all = [...r.warnings, ...r2.warnings, ...up.warnings];
    for (const x of all) expect([x.text, x.baseSeverity]).toEqual(spec[x.id]);
    expect(new Set(all.map((x) => x.id))).toEqual(new Set(Object.keys(spec)));
  });
  it("sorts Critical first, Positive last", () => {
    const order = { Critical: 0, High: 1, Moderate: 2, Positive: 3 } as const;
    const r = mock({ rec: [null, null, null, null, null, 100, 300] });
    expect(r.warnings.map((x) => order[x.severity])).toEqual([...r.warnings.map((x) => order[x.severity])].sort());
  });
});
