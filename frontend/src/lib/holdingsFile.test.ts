import { describe, expect, it } from "vitest";
import * as XLSX from "xlsx";
import { ACCEPT, gridFromText, gridsFromFile, namesFromFile, namesFromGrid, plausibleName, tidy } from "./holdingsFile";
import { makeMatcher } from "./holdingsMatch";
import type { SearchRow } from "./api";

const INDEX: SearchRow[] = ([
  ["RELIANCE", "Reliance Industries Ltd.", "500325"], ["TCS", "Tata Consultancy Services Ltd.", "532540"],
  ["HDFCBANK", "HDFC Bank Ltd.", "500180"], ["INFY", "Infosys Ltd.", "500209"], ["ICICIBANK", "ICICI Bank Ltd.", "532174"],
  ["ITC", "ITC Ltd.", "500875"], ["LT", "Larsen & Toubro Ltd.", "500510"], ["SBIN", "State Bank of India", "500112"],
  ["BHARTIARTL", "Bharti Airtel Ltd.", "532454"], ["HINDUNILVR", "Hindustan Unilever Ltd.", "500696"],
  ["KOTAKBANK", "Kotak Mahindra Bank Ltd.", "500247"], ["AXISBANK", "Axis Bank Ltd.", "532215"],
  ["ASIANPAINT", "Asian Paints Ltd.", "500820"], ["MARUTI", "Maruti Suzuki India Ltd.", "532500"],
  ["SUNPHARMA", "Sun Pharmaceutical Industries Ltd.", "524715"], ["TATAMOTORS", "Tata Motors Ltd.", "500570"],
  ["TATASTEEL", "Tata Steel Ltd.", "500470"], ["WIPRO", "Wipro Ltd.", "507685"], ["TITAN", "Titan Company Ltd.", "500114"],
  ["ULTRACEMCO", "UltraTech Cement Ltd.", "532538"], ["NESTLEIND", "Nestle India Ltd.", "500790"],
  ["BAJFINANCE", "Bajaj Finance Ltd.", "500034"], ["M&M", "Mahindra & Mahindra Ltd.", "500520"],
  ["ONGC", "Oil & Natural Gas Corporation Ltd.", "500312"], ["NTPC", "NTPC Ltd.", "532555"], ["POWERGRID", "Power Grid Corporation of India Ltd.", "532898"],
  ["COALINDIA", "Coal India Ltd.", "533278"], ["ADANIENT", "Adani Enterprises Ltd.", "512599"], ["ZOMATO", "Zomato Ltd.", "543320"],
  ["IRCTC", "Indian Railway Catering and Tourism Corporation Ltd.", "542830"],
] as [string, string, string][]).map(([s, n, b]) => [s, n, b, 1, s] as SearchRow);
const matches = makeMatcher(INDEX)!;

const f = (parts: BlobPart[], name: string) => new File(parts, name);
const book = (sheets: Record<string, unknown[][]>, bookType: "xlsx" | "xls" | "ods", name: string) => {
  const wb = XLSX.utils.book_new();
  for (const [n, rows] of Object.entries(sheets)) XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(rows), n);
  const out = XLSX.write(wb, { type: "array", bookType }) as ArrayBuffer;
  return f([out], name);
};

const zerodhaRows = (): unknown[][] => [
  ["Equity Holdings Statement as on 2024-11-05"], [], ["Client ID", "AB1234"], ["Name", "TEST USER"], [], ["Summary"], [],
  ["Invested Value", 123456.5], ["Present Value", 150000.25], ["Unrealised P&L", 26543.75], [], [], [], [], [], [], [],
  ["Instrument", "Qty.", "Avg. cost", "LTP", "Cur. val", "P&L", "Net chg.", "Day chg."],
  ["RELIANCE", 10, 2400.5, 2900.1, 29001, 4996, "20.7%", "0.5%"], ["TCS", 5, 3200, 4100, 20500, 4500, "28%", "-0.3%"],
  ["HDFCBANK", 25, 1500, 1650, 41250, 3750, "10%", "1%"], ["INFY", 12, 1400, 1800, 21600, 4800, "28%", "0%"],
  ["ITC", 100, 300, 450, 45000, 15000, "50%", "1.2%"], ["LT", 7, 2500, 3500, 24500, 7000, "40%", "0%"], ["TATAMOTORS", 40, 400, 950, 38000, 22000, "137%", "2%"],
];

describe("Zerodha Console holdings", () => {
  it("skips the ~17 row title block (xlsx)", async () => {
    const names = await namesFromFile(book({ Equity: zerodhaRows() }, "xlsx", "holdings.xlsx"), matches);
    expect(names).toEqual(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "LT", "TATAMOTORS"]);
  });
  it("works as legacy .xls BIFF", async () => {
    const names = await namesFromFile(book({ Equity: zerodhaRows() }, "xls", "holdings.xls"), matches);
    expect(names).toEqual(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "LT", "TATAMOTORS"]);
  });
  it("works as .ods", async () => {
    const names = await namesFromFile(book({ Equity: zerodhaRows() }, "ods", "holdings.ods"), matches);
    expect(names).toHaveLength(7);
  });
  it("works without a matcher (header-based)", async () => {
    const names = await namesFromFile(book({ Equity: zerodhaRows() }, "xlsx", "holdings.xlsx"));
    expect(names).toEqual(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "LT", "TATAMOTORS"]);
  });
  it("never returns numbers, percentages or P&L labels", async () => {
    const names = await namesFromFile(book({ Equity: zerodhaRows() }, "xlsx", "h.xlsx"), matches);
    for (const n of names) expect(n).toMatch(/[A-Z]/);
    expect(names.join("|")).not.toMatch(/Unrealised|Invested|Present|Client|TEST USER/i);
  });
});

describe("Groww", () => {
  const rows: unknown[][] = [
    ["Name", "Test User"], ["Unique Client Code (UCC)", "1234567890"], ["Email", "a@b.com"], [], ["Holdings statement for stocks as on 05-11-2024"], [],
    ["Stock Name", "ISIN", "Quantity", "Average buy price", "Buy value", "Closing price", "Closing value", "Unrealised P&L"],
    ["Reliance Industries Ltd", "INE002A01018", 10, 2400, 24000, 2900, 29000, 5000], ["Tata Consultancy Services Ltd", "INE467B01029", 5, 3200, 16000, 4100, 20500, 4500],
    ["HDFC Bank Ltd", "INE040A01034", 25, 1500, 37500, 1650, 41250, 3750], ["Infosys Ltd", "INE009A01021", 12, 1400, 16800, 1800, 21600, 4800],
    ["Larsen & Toubro Ltd", "INE018A01030", 7, 2500, 17500, 3500, 24500, 7000],
    [], ["Total", "", "", "", 111800, "", 137000, 25200], ["Disclaimer: values are indicative."],
  ];
  it("takes the Stock Name column, not ISINs", async () => {
    const names = await namesFromFile(book({ Sheet1: rows }, "xlsx", "groww.xlsx"), matches);
    expect(names).toEqual(["Reliance Industries Ltd", "Tata Consultancy Services Ltd", "HDFC Bank Ltd", "Infosys Ltd", "Larsen & Toubro Ltd"]);
  });
  it("same without a matcher", async () => {
    expect(await namesFromFile(book({ Sheet1: rows }, "xls", "groww.xls"))).toHaveLength(5);
  });
});

describe("Upstox / Angel One / ICICI Direct / HDFC Securities / Dhan / Kotak", () => {
  it("Upstox csv (Company Name, ISIN, Quantity, Avg Price, LTP)", async () => {
    const csv = "Company Name,ISIN,Quantity,Average Price,Last Traded Price,P&L\nTata Motors Ltd,INE155A01022,40,400,950,22000\nITC Ltd,INE154A01025,100,300,450,15000\n";
    expect(await namesFromFile(f([csv], "upstox.csv"), matches)).toEqual(["Tata Motors Ltd", "ITC Ltd"]);
  });
  it("Angel One xlsx with Symbol Name + exchange columns", async () => {
    const rows = [["Holdings"], ["Symbol Name", "Exchange", "Quantity", "Avg Price", "LTP"], ["INFY", "NSE", 12, 1400, 1800], ["WIPRO", "NSE", 5, 400, 500]];
    expect(await namesFromFile(book({ H: rows }, "xlsx", "angel.xlsx"), matches)).toEqual(["INFY", "WIPRO"]);
  });
  it("ICICI Direct / HDFC Securities: Stock Symbol and Company Name both present", async () => {
    const rows = [["Stock Symbol", "Company Name", "ISIN", "Qty", "Average Cost Price", "Current Market Price", "Value Of Holdings", "Realized Profit"],
      ["RELIND", "RELIANCE INDUSTRIES LTD", "INE002A01018", 10, 2400, 2900, 29000, 0], ["INFTEC", "INFOSYS LTD", "INE009A01021", 12, 1400, 1800, 21600, 0],
      ["HDFBAN", "HDFC BANK LTD", "INE040A01034", 25, 1500, 1650, 41250, 0]];
    const names = await namesFromFile(book({ H: rows }, "xlsx", "icici.xlsx"), matches);
    expect(names).toEqual(["RELIANCE INDUSTRIES LTD", "INFOSYS LTD", "HDFC BANK LTD"]);
    // without a matcher the symbol-ish column is preferred by header, but still never ISIN/numbers
    const plain = await namesFromFile(book({ H: rows }, "xlsx", "icici.xlsx"));
    expect(plain.length).toBe(3);
    for (const n of plain) expect(n).not.toMatch(/^INE/);
  });
  it("Dhan / Kotak: Scrip Name with -EQ suffixes and BSE/NSE prefixes", async () => {
    const rows = [["Scrip Name", "Net Qty", "Avg Price", "LTP"], ["RELIANCE-EQ", 10, 1, 2], ["TCS - EQ", 5, 1, 2], ["HDFCBANK EQ", 5, 1, 2], ["INFY.NS", 1, 1, 2], ["NSE:ITC", 1, 1, 2], ["TATAMOTORS-BE", 1, 1, 2]];
    const names = await namesFromFile(book({ S: rows }, "xlsx", "dhan.xlsx"), matches);
    expect(names).toHaveLength(6);
    expect(names.map(tidy)).toEqual(["RELIANCE", "TCS", "HDFCBANK", "INFY", "ITC", "TATAMOTORS"]);
  });
  it("Zerodha-style 'M&M' keeps its ampersand", () => {
    expect(namesFromGrid([["Instrument", "Qty."], ["M&M", "3"], ["TCS", "2"]], matches)).toEqual(["M&M", "TCS"]);
  });
});

describe("headerless and odd layouts", () => {
  it("no header row: finds the name column by matching companies", async () => {
    const rows = [["INE002A01018", "Reliance Industries Ltd", 10, 2400], ["INE467B01029", "Tata Consultancy Services Ltd", 5, 3200], ["INE009A01021", "Infosys Ltd", 1, 5]];
    expect(await namesFromFile(book({ S: rows }, "xlsx", "nohead.xlsx"), matches)).toEqual(["Reliance Industries Ltd", "Tata Consultancy Services Ltd", "Infosys Ltd"]);
  });
  it("no header, name not first column, quantity first", async () => {
    const rows = [[10, "RELIANCE", 2900], [5, "TCS", 4100], [3, "ITC", 450]];
    expect(await namesFromFile(book({ S: rows }, "xlsx", "n.xlsx"), matches)).toEqual(["RELIANCE", "TCS", "ITC"]);
  });
  it("ISIN column then a name column", () => {
    const g = [["ISIN", "Name", "Qty"], ["INE002A01018", "Reliance Industries", "10"], ["INE467B01029", "TCS", "5"]];
    expect(namesFromGrid(g, matches)).toEqual(["Reliance Industries", "TCS"]);
    expect(namesFromGrid(g)).toEqual(["Reliance Industries", "TCS"]);
  });
  it("ISIN-only column (nothing else) yields no fake names", () => {
    const g = [["ISIN", "Qty"], ["INE002A01018", "10"], ["INE467B01029", "5"]];
    expect(namesFromGrid(g, matches)).toEqual([]);
  });
  it("pasted names without header use the first column (no matcher)", () => {
    expect(namesFromGrid(gridFromText("Reliance\nTCS\nInfosys"))).toEqual(["Reliance", "TCS", "Infosys"]);
  });
  it("header only in a later row of a sheet that starts with a title", () => {
    const g = [["My holdings"], ["", ""], ["Company", "Shares"], ["Infosys Ltd", "5"], ["Wipro Ltd", "2"]];
    expect(namesFromGrid(g)).toEqual(["Infosys Ltd", "Wipro Ltd"]);
  });
  it("a 'Name:' title line before the header does not hijack the name column", () => {
    const g = [["Name", "TEST USER"], ["Client ID", "X"], ["Stock Name", "Qty"], ["Infosys Ltd", "5"], ["Wipro Ltd", "2"]];
    expect(namesFromGrid(g, matches)).toEqual(["Infosys Ltd", "Wipro Ltd"]);
    expect(namesFromGrid(g)).toEqual(["Infosys Ltd", "Wipro Ltd"]);
  });
  it("empty and tiny grids", () => {
    expect(namesFromGrid([])).toEqual([]);
    expect(namesFromGrid([[]])).toEqual([]);
    expect(namesFromGrid([["Instrument"]])).toEqual([]);
  });
  it("de-duplicates repeated names", () => {
    expect(namesFromGrid([["Instrument", "Qty"], ["TCS", "1"], ["TCS", "2"]])).toEqual(["TCS"]);
  });
  it("ragged rows (shorter than header) do not throw", () => {
    expect(namesFromGrid([["Instrument", "Qty", "LTP"], ["TCS"], ["ITC", "4"]], matches)).toEqual(["TCS", "ITC"]);
  });
});

describe("text formats", () => {
  it("semicolon csv", async () => {
    const csv = "Instrument;Qty;LTP\nRELIANCE;10;2900,50\nTCS;5;4100,25\n";
    expect(await namesFromFile(f([csv], "h.csv"), matches)).toEqual(["RELIANCE", "TCS"]);
  });
  it("tab separated", async () => {
    const tsv = "Stock Name\tISIN\tQty\nInfosys Ltd\tINE009A01021\t3\nITC Ltd\tINE154A01025\t4\n";
    expect(await namesFromFile(f([tsv], "h.tsv"), matches)).toEqual(["Infosys Ltd", "ITC Ltd"]);
    expect(await namesFromFile(f([tsv], "h.txt"), matches)).toEqual(["Infosys Ltd", "ITC Ltd"]);
  });
  it("quoted comma inside a name", async () => {
    const csv = 'Stock Name,Qty,Avg\n"Larsen & Toubro Ltd., Mumbai",5,3000\n"Tata Motors Ltd",5,400\n';
    const grid = gridFromText(csv);
    expect(grid[1][0]).toBe("Larsen & Toubro Ltd., Mumbai");
    expect(grid[1]).toHaveLength(3);
    const names = await namesFromFile(f([csv], "q.csv"), matches);
    expect(names).toHaveLength(2);
    expect(matches(names[0])).toBe(true);
  });
  it("embedded newline in a quoted cell and doubled quotes", () => {
    const g = gridFromText('A,B\n"x ""y""\nz",2\n');
    expect(g[1]).toEqual(['x "y"\nz', "2"]);
  });
  it("UTF-8 BOM", async () => {
    const csv = "﻿Instrument,Qty\nTCS,3\nITC,4\n";
    expect(await namesFromFile(f([csv], "bom.csv"), matches)).toEqual(["TCS", "ITC"]);
    expect(await namesFromFile(f([new Uint8Array([0xef, 0xbb, 0xbf, ...new TextEncoder().encode("Instrument,Qty\nTCS,3\n")])], "bom2.csv"))).toEqual(["TCS"]);
  });
  it("CRLF and old-Mac CR line endings", () => {
    expect(gridFromText("Instrument,Qty\r\nTCS,3\r\nITC,4\r\n")).toHaveLength(3);
    expect(gridFromText("Instrument,Qty\rTCS,3\rITC,4\r")).toHaveLength(3);
  });
  it("delimiter in the title line does not break delimiter detection of the table", () => {
    const csv = "Holdings as on 05-11-2024, generated by broker\nInstrument,Qty,LTP\nTCS,3,4000\nITC,4,450\n";
    expect(namesFromGrid(gridFromText(csv), matches)).toEqual(["TCS", "ITC"]);
  });
  it("tab file whose title line has no tab", () => {
    const tsv = "Holdings Statement\n\nInstrument\tQty\tLTP\nTCS\t3\t4000\nITC\t4\t450\n";
    expect(namesFromGrid(gridFromText(tsv), matches)).toEqual(["TCS", "ITC"]);
  });
  it("semicolon file whose title line has no semicolon", () => {
    const t = "Holdings Statement\nInstrument;Qty;LTP\nTCS;3;4000\nITC;4;450\n";
    expect(namesFromGrid(gridFromText(t), matches)).toEqual(["TCS", "ITC"]);
  });
  it("HTML table disguised as .xls", async () => {
    const html = `<html><head><meta charset="utf-8"></head><body><h3>Holdings</h3><table border=1>
      <tr><th>Scrip Name</th><th>Qty</th><th>Value</th></tr>
      <tr><td>Reliance Industries Ltd</td><td>10</td><td>29,000.00</td></tr>
      <tr><td>Infosys Ltd</td><td>12</td><td>21,600.00</td></tr>
      <tr><td>Total</td><td>22</td><td>50,600.00</td></tr></table></body></html>`;
    expect(await namesFromFile(f([html], "holdings.xls"), matches)).toEqual(["Reliance Industries Ltd", "Infosys Ltd"]);
    expect(await namesFromFile(f([html], "holdings.html"))).toEqual(["Reliance Industries Ltd", "Infosys Ltd"]);
  });
  it("HTML with &amp; entity in a name", async () => {
    const html = "<table><tr><td>Stock</td><td>Qty</td></tr><tr><td>Larsen &amp; Toubro Ltd</td><td>3</td></tr><tr><td>ITC Ltd</td><td>3</td></tr></table>";
    expect(await namesFromFile(f([html], "x.xls"), matches)).toEqual(["Larsen & Toubro Ltd", "ITC Ltd"]);
  });
  it("csv mislabeled as .xls still reads", async () => {
    expect(await namesFromFile(f(["Instrument,Qty\nTCS,3\nITC,4\n"], "h.xls"), matches)).toEqual(["TCS", "ITC"]);
  });
  it("ACCEPT lists the supported extensions", () => {
    for (const e of [".xlsx", ".xls", ".ods", ".csv", ".tsv", ".txt", ".html"]) expect(ACCEPT).toContain(e);
  });
});

describe("totals, notes and multiple sheets", () => {
  it("stops at a Total row and ignores disclaimers", () => {
    const g = [["Instrument", "Qty", "Cur. val"], ["TCS", "3", "12000"], ["ITC", "4", "1800"], ["Total", "", "13800"], ["Note: prices delayed", ""], ["Disclaimer text goes here", ""]];
    expect(namesFromGrid(g, matches)).toEqual(["TCS", "ITC"]);
    expect(namesFromGrid(g)).toEqual(["TCS", "ITC"]);
  });
  it("Total in a non-name column on a data row does not truncate real data", () => {
    // a company called 'Total ...' is unusual; but a stray 'Total' text in the qty column must be only the summary row
    const g = [["Instrument", "Qty"], ["TCS", "3"], ["Grand Total", "7"]];
    expect(namesFromGrid(g)).toEqual(["TCS"]);
  });
  it("a listed company whose name starts with 'Total' is not treated as the summary row", () => {
    const g = [["Instrument", "Qty"], ["TCS", "3"], ["Totalenergies Ltd", "1"], ["ITC", "2"]];
    expect(namesFromGrid(g)).toEqual(["TCS", "Totalenergies Ltd", "ITC"]);
  });
  it("total row appearing before any data (header then Total first) leaves later rows alone", () => {
    const g = [["Instrument", "Qty"], ["Total", "7"], ["TCS", "3"]];
    expect(namesFromGrid(g)).toEqual(["TCS"]);
  });
  it("Equity sheet beats Mutual Funds sheet", async () => {
    const eq = [["Instrument", "Qty"], ["RELIANCE", 1], ["TCS", 2], ["INFY", 3]];
    const mf = [["Scheme Name", "Units", "NAV"], ["Axis Bluechip Fund - Direct Growth", 10, 50], ["Parag Parikh Flexi Cap Fund", 3, 60], ["SBI Small Cap Fund", 2, 20], ["HDFC Mid-Cap Opportunities Fund", 4, 90]];
    for (const order of [["Mutual Funds", "Equity"], ["Equity", "Mutual Funds"]]) {
      const sheets: Record<string, unknown[][]> = {};
      for (const n of order) sheets[n] = n === "Equity" ? eq : mf;
      expect(await namesFromFile(book(sheets, "xlsx", "m.xlsx"), matches)).toEqual(["RELIANCE", "TCS", "INFY"]);
    }
  });
  it("mutual fund names are not matched as shares by the matcher", () => {
    for (const n of ["Axis Bluechip Fund - Direct Growth", "Parag Parikh Flexi Cap Fund", "SBI Small Cap Fund", "HDFC Mid-Cap Opportunities Fund"]) expect(matches(n)).toBe(false);
  });
  it("without a matcher, equity sheet is still not lost behind a longer MF sheet", async () => {
    const eq = [["Instrument", "Qty"], ["RELIANCE", 1], ["TCS", 2]];
    const mf = [["Scheme Name", "Units"], ["A Fund", 1], ["B Fund", 1], ["C Fund", 1]];
    const names = await namesFromFile(book({ Equity: eq, MF: mf }, "xlsx", "m.xlsx"));
    expect(names.length).toBeGreaterThan(0);
  });
  it("an empty first sheet does not win", async () => {
    const names = await namesFromFile(book({ Cover: [["Welcome"]], Equity: [["Instrument", "Qty"], ["TCS", 2]] }, "xlsx", "m.xlsx"), matches);
    expect(names).toEqual(["TCS"]);
  });
});

describe("numbers and dates stored natively", () => {
  it("numeric cells are never names", async () => {
    const rows = [["Instrument", "Qty", "Price", "Date"], ["TCS", 3, 4100.55, new Date(Date.UTC(2024, 10, 5))], ["ITC", 4, 450, new Date(Date.UTC(2024, 10, 6))], [12345, 1, 1, 1], [543320, 1, 2, 3]];
    const wb = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(rows), "S");
    const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" }) as ArrayBuffer;
    const names = await namesFromFile(f([buf], "n.xlsx"), matches);
    expect(names.slice(0, 2)).toEqual(["TCS", "ITC"]);
    expect(names).not.toContain("12345");
  });
  it("formatted numbers with currency/commas are not names", () => {
    for (const s of ["₹1,23,456.78", "-12.5%", "(1,200.00)", "05/11/2024", "10:30", "2024-11-05"]) expect(plausibleName(s)).toBe(false);
  });
});

describe("plausibleName / tidy", () => {
  it("rejects labels, ISINs and junk", () => {
    for (const s of ["", " ", "A", "Total", "Grand Total", "Equity", "ISIN", "INE002A01018", "x".repeat(81)]) expect(plausibleName(s)).toBe(false);
  });
  it("accepts names and a BSE code", () => {
    for (const s of ["TCS", "HDFC Bank Ltd", "500325", "M&M", "Bajaj Auto", "3M India", "20 Microns"]) expect(plausibleName(s)).toBe(true);
  });
  it("does not reject companies that merely start with a label word", () => {
    for (const s of ["Netweb Technologies", "Currentware Ltd", "Dalmia Bharat", "Idea Cellular", "Cashbridge Ltd", "Equitas Small Finance Bank", "Datamatics Global", "Panacea Biotec", "Dpsc Ltd", "National Aluminium", "Client Services Ltd", "Marginal Ltd", "Holdings Ltd"]) expect(plausibleName(s), s).toBe(true);
  });
  it("tidy", () => {
    expect(tidy("TCS-EQ")).toBe("TCS");
    expect(tidy("RELIANCE EQ")).toBe("RELIANCE");
    expect(tidy("INFY - BE")).toBe("INFY");
    expect(tidy("HDFCBANK.NS")).toBe("HDFCBANK");
    expect(tidy("SBIN.BO")).toBe("SBIN");
    expect(tidy("NSE: ITC")).toBe("ITC");
    expect(tidy("ITC LTD. EQ")).toBe("ITC LTD.");
    expect(tidy("ITC (EQ)")).toBe("ITC");
    expect(tidy("  Bajaj  Auto\t ")).toBe("Bajaj Auto");
    expect(tidy("M&M")).toBe("M&M");
    expect(tidy("BAJAJ-AUTO")).toBe("BAJAJ-AUTO");
    expect(tidy("NESTLEIND-EQ")).toBe("NESTLEIND");
  });
});

describe("limits and bad files", () => {
  it("rejects files over 5 MB without reading them", async () => {
    const big = f([new Uint8Array(5_000_001)], "big.csv");
    await expect(gridsFromFile(big)).rejects.toThrow(/5 MB/);
    await expect(namesFromFile(big, matches)).rejects.toThrow(/5 MB/);
  });
  it("accepts a file just under the limit", async () => {
    const line = "TCS,1\n";
    const body = "Instrument,Qty\n" + line.repeat(Math.floor(4_900_000 / line.length));
    const names = await namesFromFile(f([body], "ok.csv"), matches);
    expect(names).toEqual(["TCS"]);
  });
  it("a corrupt xlsx (zip magic, garbage) throws or yields nothing, never hangs", async () => {
    const junk = new Uint8Array(2000); junk[0] = 0x50; junk[1] = 0x4b; for (let i = 2; i < junk.length; i++) junk[i] = (i * 31) & 255;
    const r = await namesFromFile(f([junk], "bad.xlsx"), matches).then((v) => ({ v }), (e) => ({ e }));
    if ("v" in r) expect(r.v).toEqual([]); else expect(r.e).toBeInstanceOf(Error);
  }, 10_000);
  it("a corrupt xls (OLE magic, garbage) throws or yields nothing", async () => {
    const junk = new Uint8Array(4000); junk.set([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]); for (let i = 8; i < junk.length; i++) junk[i] = (i * 17) & 255;
    const r = await namesFromFile(f([junk], "bad.xls"), matches).then((v) => ({ v }), (e) => ({ e }));
    if ("v" in r) expect(r.v).toEqual([]); else expect(r.e).toBeInstanceOf(Error);
  }, 10_000);
  it("binary garbage named .xlsx without any magic fails cleanly", async () => {
    const junk = new Uint8Array(3000); for (let i = 0; i < junk.length; i++) junk[i] = (i * 7 + 3) & 255;
    const r = await namesFromFile(f([junk], "bad2.xlsx"), matches).then((v) => ({ v }), (e) => ({ e }));
    if ("v" in r) expect(r.v).toEqual([]); else expect(r.e).toBeInstanceOf(Error);
  }, 10_000);
  it("an empty file gives no names", async () => {
    expect(await namesFromFile(f([""], "e.csv"), matches)).toEqual([]);
    const r = await namesFromFile(f([""], "e.xlsx"), matches).then((v) => ({ v }), (e) => ({ e }));
    if ("v" in r) expect(r.v).toEqual([]); else expect(r.e).toBeInstanceOf(Error);
  });
  it("more than 5000 rows is capped, not slow", async () => {
    const rows: unknown[][] = [["Instrument", "Qty"]];
    for (let i = 0; i < 7000; i++) rows.push(["TCS" + i, 1]);
    const t = Date.now();
    const names = await namesFromFile(book({ S: rows }, "xlsx", "many.xlsx"));
    expect(names.length).toBeLessThanOrEqual(5000);
    expect(Date.now() - t).toBeLessThan(8000);
  }, 15_000);
});
