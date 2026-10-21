/** Home-page questions, grouped. Answers describe what the live site does today; planned items are labelled as planned.
 *  Facts checked against backend/finlit/auth/entitlements.py, alertengine.py and the pages themselves. */
export type FaqGroup = { title: string; items: [string, string][] };

export const FAQ_GROUPS: FaqGroup[] = [
  { title: "Getting started", items: [
    ["What can I do with FinLit Ventures?", "Search Indian stocks with filters, read a company's financial statements, see our score for it, keep watchlists and set alerts on numbers you care about. Basic is free."],
    ["How do I find stocks that match my criteria?", "Open the Screener. Choose a size (large, mid or small cap), an industry, and then add filters such as P/E, ROE, growth or debt. Basic has 14 filters. Silver opens all 160+, and Gold adds filters built on the FinLit score."],
    ["Can I research a single company?", "Yes. Search for any listed company. Its page shows profit and loss, balance sheet, cash flow, valuation, shareholding, a price chart, peers and filings."],
    ["What is FinLit?", "FinLit Ventures is a small research and technology company. We build the research pages and tools on this site, and we also run paid sessions on portfolio review and financial planning. See the Services page."],
  ] },
  { title: "Screening and scoring", items: [
    ["How does the screener work?", "You set rules, and it shows the companies that pass all of them: size, sector, index and any financial filter. Results update as you change a rule. Silver and Gold members can save a screen, share its link and download the matches as a CSV."],
    ["What is the difference between a fundamental and a technical score?", "Fundamental looks at the business: quality, growth, profitability and balance sheet. Technical looks only at the share price: its trend and momentum. The score screener shows them as separate columns. The overall FinLit score is the average of all five pillars, so it does include the technical one."],
    ["What does the model score look at?", "Five pillars, each from 0 to 100: Quality, Growth, Profitability, Balance sheet and Technical. The overall score is their average. Each company page shows which numbers went into each pillar."],
    ["Does a high score mean I should buy the stock?", "No. A score helps you compare companies and decide what to read first. It does not predict returns and it is not a recommendation. Do your own research and think about your own risk."],
  ] },
  { title: "Company research", items: [
    ["Which financial statements can I see?", "Profit and loss, balance sheet and cash flow, yearly and quarterly, plus ratios and the shareholding pattern. These are free for everyone. Gold adds the full ratio history."],
    ["How do I compare two companies?", "Use Compare to see two companies side by side: valuation, growth, profitability, debt and more. Silver adds the score-based tabs. Gold lets you compare four at once. Companies from the same industry give the fairest comparison."],
    ["How do I understand an unfamiliar term?", "Open the glossary. It has 292 terms in plain English with formulas. You can also hover over the small info mark next to a ratio."],
    ["Where does the data come from?", "From market-data providers and exchange filings. Each company page shows when it was last updated. Figures that fail our checks are not published. Data can still be delayed or wrong, so check important numbers against the company's own filings."],
  ] },
  { title: "Tracking and portfolio", items: [
    ["How do alerts work?", "Pick a company and a condition, for example price above a level, RSI below 30 or a results date announced. We tell you in the app, and by email if you choose. Basic allows 3 alerts, Silver 30 and Gold 300. Some conditions, such as P/E and the FinLit score, start at Silver. Some conditions are checked live and others once a day."],
    ["Can I keep a watchlist?", "Yes, from Silver. Silver gives you 3 named lists and 30 stocks in total, with notes and target prices. Gold gives you up to 50 lists and 1,000 stocks, and can group them by FinLit band and style."],
    ["Can I analyse my own portfolio?", "Partly. From Silver, you can add the shares you hold by typing, pasting or uploading an Excel or CSV file from your broker (up to 30 on Silver, 500 on Gold). We only read the share names. You get each share's FinLit score, your portfolio's average score and your sector mix. We do not ask for quantities or prices, so it does not show your profit and loss or portfolio value. PDF statements are not supported yet."],
  ] },
  { title: "Plans and access", items: [
    ["What is the difference between Basic, Silver and Gold?", "Basic is free: statements, key ratios, shareholding, a starter screener with 14 filters, comparing two companies, the glossary, calendars and 3 alerts. Silver adds the full screener, the FinLit score and its five pillars, watchlists, the portfolio scorecard and downloads. Gold adds the model filters in the screener, the full ratio history, technical analysis, comparing four companies and the Gold dashboards. Open the Plans page for the full table."],
    ["Are equity research reports available now?", "Not yet. A full written equity research report is planned for later, and we will only offer it once the licence and approvals it needs are in place. Meanwhile, Gold members can print a Premium Report for any company, which is built from our data and is not a written opinion."],
    ["How do I upgrade or cancel?", "Online payment is not live yet. Open Account, then Plan, and request Silver or Gold. Our team switches the plan on for your account. To change or end a plan, write to us."],
    ["Is this investment advice?", "No. FinLit is not registered with SEBI or AMFI. Everything here is for information and learning, and it is not an offer or a recommendation to buy or sell anything. Your decisions and risks are yours."],
    ["Is my data safe?", "Passwords are stored as one-way hashes, so we cannot read them. You can see and end your sessions on any device. Administrator accounts need an authenticator app. We never ask for your broker password."],
  ] },
];
