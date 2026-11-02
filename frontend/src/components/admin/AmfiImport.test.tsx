import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../lib/ui", () => ({ useUI: () => ({ toast: () => undefined }) }));
vi.mock("@tanstack/react-query", () => ({ useMutation: () => ({ isPending: false, mutate: () => undefined }) }));
import { AUM_LINKS, AmfiImport, terLinks } from "./AmfiImport";

describe("AMFI import panel", () => {
  it("links this month's and last month's expense-ratio files, in the form AMFI lists (MM-YYYY), across a year end", () => {
    expect(terLinks(new Date(2026, 10, 2)).map((l) => l.month)).toEqual(["11-2026", "10-2026"]);
    expect(terLinks(new Date(2027, 0, 15)).map((l) => l.month)).toEqual(["01-2027", "12-2026"]);
    expect(terLinks(new Date(2026, 10, 2))[1].url).toBe("https://www.amfiindia.com/api/populate-te-rdata-revised?MF_ID=All&Month=10-2026&strCat=-1&strType=-1&excel=true");
  });
  it("links the four quarters of the average-AUM page", () => {
    expect(AUM_LINKS).toHaveLength(4);
    expect(AUM_LINKS[0].url).toBe("https://www.amfiindia.com/api/average-aum-schemewise?strType=Typewise&fyId=1&periodId=1");
  });
  it("explains the problem, offers both uploads and never advises", () => {
    const out = renderToStaticMarkup(<AmfiImport />);
    for (const t of ["Expense ratios and fund sizes (AMFI)", "Upload the expense-ratio file", "Upload the fund-size file", "does not answer from the server"]) expect(out).toContain(t);
    expect(out.replace(/<[^>]*>/g, " ")).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target|best)\b/i);   // visible words only, not link attributes
  });
});
