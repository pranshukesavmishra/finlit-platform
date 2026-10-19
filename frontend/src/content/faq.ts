/** Home-page questions, grouped. Answers describe what the live site does today; planned items are labelled as planned. */
export type FaqGroup = { title: string; items: [string, string][] };

export const FAQ_GROUPS: FaqGroup[] = [
  { title: "Getting started", items: [
    ["What can I do with FinLit Ventures?", "Discover Indian stocks with filters, judge companies with separate fundamental and technical scores, read their financial statements, build watchlists and set alerts on the metrics you care about."],
    ["How do I find stocks that match my criteria?", "Open the Screener. Pick a size (large, mid or small cap), an industry or sector, then add filters such as valuation, profitability, growth or debt. Silver adds the full set of 160+ filters, and Gold adds filters built on the FinLit model scores."],
    ["Can I research a single company?", "Yes. Search for any listed company to see its profit and loss, balance sheet, cash flow, valuation, shareholding pattern, price chart, peers and filings, all on one page."],
    ["What is FinLit?", "FinLit Ventures is a research and technology company. We publish a research report for every listed Indian stock, review portfolios and help people plan their investing."],
  ] },
  { title: "Screening and scoring", items: [
    ["How does the screener work?", "You narrow the whole market down with rules you choose: size, sector, index membership and any of the financial filters. Results update as you type, and you can save a screen, share its link or download the matches (Silver and Gold)."],
    ["What is the difference between a fundamental and a technical score?", "The fundamental score looks at the business: quality, growth, profitability and balance sheet. The technical score looks only at the share price: trend and momentum. We show them side by side and never blend them into one number, so you can read each on its own."],
    ["What does the model score look at?", "Five pillars, each from 0 to 100: Quality, Growth, Profitability, Balance sheet (the four fundamental pillars) and Technical. Every report shows which numbers went into each pillar and how they were read."],
    ["Does a high score mean I should buy the stock?", "No. A score is a way to compare companies and organise your research. It does not predict returns and it is not a recommendation. Always do your own research and consider your own risk."],
  ] },
  { title: "Company research", items: [
    ["Which financial statements can I see?", "Profit and loss, balance sheet and cash flow, yearly and quarterly, together with ratios and the shareholding pattern. Statements, key ratios and shareholding are free for everyone."],
    ["How do I compare two companies?", "Use Compare to put two companies side by side, or up to four with Gold. You see valuation, growth, profitability, debt and the five pillars together. Picking two companies from the same industry gives the fairest comparison."],
    ["How do I understand an unfamiliar term?", "Open the glossary: plain-English meanings and formulas for the financial terms used across the site. Hover the small info mark next to any ratio to see what it means."],
    ["Where does the data come from?", "Financial statements, prices and filings come from licensed market-data feeds and exchange disclosures. Every report shows when it was last updated, and numbers that fail our checks are not published."],
  ] },
  { title: "Tracking and portfolio", items: [
    ["How do alerts work?", "Choose a company and a condition, for example P/E above a level, RSI below 30 or a results date announced. We tell you in the app, and by email if you choose, as soon as the condition is met. Alerts are checked when our data updates."],
    ["Can I keep a watchlist?", "Yes. Silver and Gold members build named lists with notes and price targets, and can group them by industry, size or FinLit band."],
    ["Can I analyse my own portfolio?", "Yes. The portfolio tracker (Silver and Gold) takes your holdings by hand or from a CSV file and shows value, profit and loss, allocation and a health read of each stock. Importing from PDF statements is not available yet."],
  ] },
  { title: "Plans and access", items: [
    ["What is the difference between Basic, Silver and Gold?", "Basic is free: financial statements, key ratios, shareholding, the starter screener, comparison of two companies, the glossary and calendars. Silver adds the full 160+ filter screener, the FinLit score across five pillars, watchlists, the portfolio tracker and downloads. Gold adds the FinLit model screener filters, advanced scoring, technical analysis, comparison of four companies and the Gold dashboards."],
    ["Are equity research reports available now?", "Full equity research reports are planned for a later stage and will be offered once the required licence and approvals are in place. Until then, Gold members can print a Premium Report for any company from our data."],
    ["How do I upgrade or cancel?", "Open Account, then Plan, and request Silver or Gold. Online payment is being added; until then our team activates your plan and you can change it at any time."],
    ["Is this investment advice?", "No. FinLit is not registered with SEBI or AMFI and everything on the site is for information and education. Decisions and risks stay with you."],
    ["Is my data safe?", "Passwords are stored with modern hashing, you can end your sessions on any device, administrators must use an authenticator app, and we never ask for your broker password."],
  ] },
];
