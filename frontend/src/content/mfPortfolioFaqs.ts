import type { PageFaq } from "./pageFaqs";

export const MF_PORTFOLIO_FAQ: PageFaq = {
  id: "mf-portfolio", title: "MF portfolio", section: "Your workspace", routes: ["/mf-portfolio"], plan: "Silver (Health Score: Gold)",
  items: [
    { q: "How do I add my mutual funds?", a: "Search a fund by name and select Add fund, or choose a file: Excel (.xlsx, .xls) or CSV, including consolidated-statement exports from CAMS, KFintech and broker apps. Company shares in the file are ignored. You do not need to enter units or amounts: the page lists the funds with their latest NAV, returns and Health Score." },
    { q: "How are the rows of a file matched to funds?", a: "By AMFI code, then ISIN, then the exact fund name with its plan and option, then a close name. A close name is only ever suggested: every row is shown as matched, needs choosing or not found, and nothing unmatched is imported." },
    { q: "What does the Health Score show here?", a: "The FinLit Mutual Fund Health Score with its four parts (Performance, Risk, Cost, Quality). It is part of the Gold plan; other plans still see the NAV and returns. It describes the fund's health from its past NAVs, costs and holdings; it is not a recommendation." },
    { q: "Why are the 1, 3 and 5 year returns blank for some funds?", a: "A fund's price history is downloaded one fund house at a time, every night. Until its fund house has been loaded the three returns show a dash and the page says so; they appear by themselves. A fund younger than 3 or 5 years has no return for that period." },
    { q: "How do the category filters work?", a: "Pick a group (Equity, Hybrid, Debt, Solution oriented, Others or All funds) and tick the categories you want. The single pie chart and the table below both show only the ticked categories." },
    { q: "What happens when the same fund appears twice?", a: "A fund appears once in your list. A line repeated in a file is counted once, and a fund you already follow is skipped." },
    { q: "How many funds can I add?", a: "The page shows your count against your plan's limit, for example 3 of 30 on Silver and 500 on Gold." },
    { q: "Can I export my list?", a: "Yes. Select Export CSV; every blank cell carries its reason in the Notes column. Information only, not investment advice." },
  ],
};
