import type { PageFaq } from "./pageFaqs";

export const MF_PORTFOLIO_FAQ: PageFaq = {
  id: "mf-portfolio", title: "MF portfolio", section: "Your workspace", routes: ["/mf-portfolio"], plan: "Silver (Health Score: Gold)",
  items: [
    { q: "How do I add my mutual funds?", a: "Search a fund and enter its units and either the average cost per unit or the amount invested (a purchase date and folio are optional), or choose a file: Excel (.xlsx, .xls) or CSV, including consolidated-statement exports from CAMS, KFintech and broker apps. Company shares in the file are ignored." },
    { q: "How are the rows of a file matched to funds?", a: "By AMFI code, then ISIN, then the exact fund name with its plan and option, then a close name. A close name is only ever suggested: every row is shown as matched, needs choosing or not found, and nothing unmatched is imported." },
    { q: "What does the Health Score show here?", a: "The FinLit Mutual Fund Health Score with its four parts (Performance, Risk, Cost, Quality). It is part of the Gold plan; other plans still see values and returns. It describes the fund's health from its past NAVs, costs and holdings; it is not a recommendation." },
    { q: "How is the current value worked out?", a: "Units multiplied by the fund's latest NAV, with the NAV date shown. The gain is the current value minus the amount invested." },
    { q: "When is XIRR shown?", a: "Only when every purchase has a date and the amount paid, and the first purchase is at least a year old. Otherwise a dash with the reason is shown." },
    { q: "What happens when the same fund appears twice?", a: "The same fund in the same folio is one holding with more than one purchase. The same fund in another folio is a separate holding. A line repeated exactly in a file is counted once, and a fund you already hold is skipped unless you choose to replace it." },
    { q: "How many funds can I add?", a: "The page shows your count against your plan's limit, for example 3 of 30 on Silver and 500 on Gold." },
    { q: "Can I export my list?", a: "Yes. Select Export CSV; every blank cell carries its reason in the Notes column. Information only, not investment advice." },
  ],
};
