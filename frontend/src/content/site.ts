// Company copy carried over from the current finlitventures.com (Financial-Portfolio repo),
// so the new site says what the company says today. One place to edit; used by every page.
export const COMPANY = {
  name: "FinLit Ventures",
  tagline: "Invest with clarity, not noise.",
  email: "finlit.start@gmail.com", // replace with the company email at launch
  linkedin: "https://www.linkedin.com/company/finlitventures/about/",
  disclaimer:
    "FinLit Ventures is a technology company and is not registered with SEBI or AMFI. Research shown here is for information only and is not investment advice.",
};

export const SERVICES = [
  { n: "01", name: "0 → 1 Investing", icon: "sprout", proposition: "Never invested? Start here.",
    desc: "We explain stocks, ETFs and mutual funds in plain language, work out how much risk you can live with, and help you pick an amount to start with. You leave with a simple plan you can follow on your own." },
  { n: "02", name: "Wealth Planning", icon: "growth", proposition: "A plan for the money you already earn and save.",
    desc: "We look at your income, savings and goals, then talk through how to split money between equity, debt, gold and cash you can reach in an emergency. We show the trade-offs. We do not promise returns." },
  { n: "03", name: "Family Financial Planning", icon: "users", proposition: "One page for the whole family's money.",
    desc: "Children's education, a home, parents' health cover, retirement. We put your goals, your investments and your insurance side by side and point out what is missing." },
  { n: "04", name: "Global Investing", icon: "map", proposition: "Thinking about investing outside India?",
    desc: "We explain the ways an Indian resident can get foreign exposure, such as international funds and ETFs, what they cost and which tax questions to check with a tax professional. We also help you decide how much, if anything, belongs in your portfolio." },
  { n: "05", name: "Portfolio Review & Stock Selection", icon: "gauge", proposition: "Already investing? Get a second pair of eyes.",
    desc: "Send us your holdings. We check how concentrated they are, where funds overlap, and what the numbers say about each company. Then we explain what we see and how we would research a new stock. We do not give buy or sell calls. You decide." },
] as const;
export type ServiceName = (typeof SERVICES)[number]["name"];

// Session prices are not decided yet: every price shows "—" until they are set here (a price is "₹…" text; per-month figures are worked out from it).
export const PRICE_TBA = "—";
/** `months` lets the Services page show the price per month. */
export const PRICING = [
  { plan: "First Session", price: PRICE_TBA, months: 0, note: "One conversation, so we can understand your goals" },
  { plan: "1 Month", price: PRICE_TBA, months: 1, note: "" },
  { plan: "3 Months", price: PRICE_TBA, months: 3, note: "" },
  { plan: "6 Months", price: PRICE_TBA, months: 6, note: "" },
  { plan: "1 Year", price: PRICE_TBA, months: 12, note: "" },
];

export const FOUNDER = {
  name: "Nishant Jain",
  role: "Independent Equity Investor & Researcher",
  credentials: ["B.Tech, IIT Kanpur", "Minor in Finance, IIT Kanpur", "CFA Level I Cleared", "NISM Certified Research Analyst"],
  bio: "Nishant studied engineering at IIT Kanpur, with a minor in finance. He looks for good businesses at sensible prices, keeps each position small enough that one mistake does not hurt, and thinks in years rather than weeks. These are his credentials, not a SEBI registration: FinLit is not registered with SEBI or AMFI.",
  linkedin: "https://www.linkedin.com/in/nishant-jain-1464071ab/",
  photo: `${import.meta.env.BASE_URL}team/nishant.webp`,
};

export const PILLARS = [
  { title: "Research", icon: "notes", text: "We read the numbers behind a company: how it earns, how much debt it carries, and whether the price asks too much." },
  { title: "Portfolio thinking", icon: "layers", text: "One good stock is not a portfolio. We look at how much you hold in each name, how the holdings overlap and what could go wrong together." },
  { title: "Explaining", icon: "users", text: "If we cannot explain why we looked at something in plain words, we do not think it is ready to show you." },
  { title: "Beyond India", icon: "map", text: "Some investors want a part of their money abroad. We explain the options, the costs and the risks, without pushing any of them." },
];

export const PRINCIPLES = [
  { title: "Think for yourself", text: "We do our own reading before we look at what everyone else is saying." },
  { title: "Keep it simple", text: "If the reasoning needs jargon to hold together, it probably does not hold together." },
  { title: "Stay steady", text: "A sound process and a position size you can sleep with matter more than this week's excitement." },
];

export const PROCESS = [
  { n: "01", title: "Idea Generation", icon: "spark", detail: "Macro & sector analysis to identify structural tailwinds and emerging themes before the crowd." },
  { n: "02", title: "Industry Analysis", icon: "factory", detail: "Top-down evaluation of industry cycles, competitive intensity and growth runways." },
  { n: "03", title: "Business Quality", icon: "quality", detail: "Bottom-up study of business quality, management integrity and durable moats." },
  { n: "04", title: "Valuation & Modelling", icon: "gauge", detail: "DCF, relative, PEG, EV/EBITDA and ROE frameworks to buy with a margin of safety." },
  { n: "05", title: "Position Sizing & Risk", icon: "balance", detail: "Disciplined sizing, stop-loss and diversification to protect capital first." },
  { n: "06", title: "Monitoring & Review", icon: "activity", detail: "Continuous tracking of thesis, earnings and price action against the plan." },
  { n: "07", title: "Exit Discipline", icon: "arrow", detail: "Systematic exits when the thesis breaks, targets hit or better opportunities emerge." },
];

export const PHILOSOPHY = ["Margin of Safety", "Business Quality", "Valuation Discipline", "Position Sizing", "Risk Management", "Patient Capital"];

export const TESTIMONIAL = {
  quote: "The portfolio review really helped me understand where my portfolio stands today. I got some idea about what decisions I can make to improve my portfolio’s performance in the near future.",
  name: "Kavya Agarwal",
};

export const WHY = {
  story: [
    "A lot of people in India already invest. Many started with a friend's tip, a few SIPs and a demat account, and never sat down to ask what the money is for.",
    "We saw three kinds of investor again and again. Some have a handful of random SIPs and no plan. Some want to start but do not know where. Some earn well and have never written down a goal.",
    "FinLit is our attempt to help with that. The website gives you free data and tools to look at companies yourself. The sessions give you a person to talk to. Neither tells you what to buy.",
  ],
  people: [
    { n: "01", title: "Scattered", text: "A few SIPs here, a stock there, and no plan tying them together.", icon: "layers" },
    { n: "02", title: "Stuck at zero", text: "Ready to start, but not sure how, how much or where.", icon: "sprout" },
    { n: "03", title: "Earning, no goals", text: "Income is fine. Nobody has asked what the savings are for.", icon: "tag" },
  ],
  suite: [
    { n: "01", title: "Research tools", text: "Free company data, a screener and a score to help you ask better questions." },
    { n: "02", title: "Portfolio review", text: "A look at how your holdings fit together." },
    { n: "03", title: "Financial planning", text: "Tie your money decisions to goals such as a home or a child's education." },
    { n: "04", title: "Wealth planning", text: "Revisit the plan as your income and life change." },
  ],
  loop: ["Look at where you are", "Spot the gaps", "Learn what you need", "Act", "Review", "Adjust"],
  principles: [
    { title: "Goals first", text: "Start with what the money is for, then pick products." },
    { title: "Portfolio before picks", text: "A stock matters for how it sits with everything else you own." },
    { title: "Review before reacting", text: "Change the plan on purpose, not because of one bad week." },
  ],
};

// Guided assistant: same menu tree as today's FinLit AI widget.
type Action = { type: "navigate"; to: string } | { type: "enquire"; service?: string } | { type: "menu"; target: string };
export type AssistantNode = { greeting?: string; prompt?: string; answer?: string; backLabel?: string; options: { label: string; action: Action }[]; additionalOptions?: { label: string; action: Action }[] };
const nav = (to: string): Action => ({ type: "navigate", to });
const enq = (service?: string): Action => ({ type: "enquire", service });
const menu = (target: string): Action => ({ type: "menu", target });
export const ASSISTANT: Record<string, AssistantNode> = {
  main: {
    greeting: "Hi, this is the FinLit assistant.\nI can point you to the right page. I cannot give investment advice.",
    prompt: "What are you looking for?",
    options: [
      { label: "Explore Services", action: menu("services") }, { label: "Portfolio Review", action: menu("portfolio-review") },
      { label: "Financial Planning", action: menu("financial-planning") }, { label: "Global Investing", action: menu("global-investing") },
    ],
    additionalOptions: [
      { label: "Performance", action: menu("performance") }, { label: "About FinLit", action: menu("about") },
      { label: "Pricing & Consultation", action: menu("pricing") }, { label: "Contact the Team", action: menu("contact") },
    ],
  },
  "financial-planning": { answer: "We offer two planning services: Wealth Planning (your own money and goals) and Family Financial Planning (the whole household). Pick one to read more.", backLabel: "Back to Main Menu",
    options: [{ label: "Wealth Planning", action: menu("wealth-planning") }, { label: "Family Financial Planning", action: menu("family-planning") }] },
  services: { answer: "We offer five services, from first-time investing to a review of what you already hold. Pick one to read more.", backLabel: "Back to Main Menu",
    options: [{ label: "0→1 Investing", action: menu("zero-to-one") }, { label: "Wealth Planning", action: menu("wealth-planning") }, { label: "Family Financial Planning", action: menu("family-planning") }, { label: "Global Investing", action: menu("global-service") }, { label: "Portfolio Review & Stock Selection", action: menu("portfolio-service") }] },
  "zero-to-one": { answer: "0→1 Investing is for people who have not started yet. We go through your goals, how much risk you can handle and how much to put in, and end with a simple plan.", backLabel: "Back to Services",
    options: [{ label: "View Services", action: nav("/services") }, { label: "Enquire About This Service", action: enq("0 → 1 Investing") }] },
  "wealth-planning": { answer: "Wealth Planning matches your investments to your goals and to how much risk you can live with, and shows how the pieces fit together.", backLabel: "Back to Services",
    options: [{ label: "View Services", action: nav("/services") }, { label: "Enquire", action: enq("Wealth Planning") }] },
  "family-planning": { answer: "Family Financial Planning puts the household's goals, investments and insurance on one page: education, a home, retirement, big expenses.", backLabel: "Back to Services",
    options: [{ label: "View Services", action: nav("/services") }, { label: "Enquire", action: enq("Family Financial Planning") }] },
  "global-investing": { answer: "Global Investing explains how Indian residents can get foreign exposure, what it costs, and how much of a portfolio it might make up.", backLabel: "Back to Main Menu",
    options: [{ label: "View Global Investing Service", action: nav("/services") }, { label: "Enquire", action: enq("Global Investing") }] },
  "global-service": { answer: "Global Investing explains how Indian residents can get foreign exposure, what it costs, and how much of a portfolio it might make up.", backLabel: "Back to Services",
    options: [{ label: "View Global Investing Service", action: nav("/services") }, { label: "Enquire", action: enq("Global Investing") }] },
  "portfolio-service": { answer: "Portfolio Review & Stock Selection looks at what you already hold, flags parts that need attention and shows how to research a new stock. We do not give buy or sell calls.", backLabel: "Back to Services",
    options: [{ label: "View Portfolio", action: nav("/portfolio") }, { label: "Enquire About Portfolio Review", action: enq("Portfolio Review & Stock Selection") }] },
  "portfolio-review": { answer: "We can review what you already hold: how much sits in each stock and sector, where holdings overlap, and why you own each one.", backLabel: "Back to Main Menu",
    options: [{ label: "View Portfolio", action: nav("/portfolio") }, { label: "Explore Portfolio Review Service", action: menu("portfolio-service") }, { label: "Enquire", action: enq("Portfolio Review & Stock Selection") }] },
  performance: { answer: "The Portfolio page shows our own realised trades from a broker statement: profit and loss, win rate and holding periods. Past results do not promise future returns.", backLabel: "Back to Main Menu",
    options: [{ label: "View Performance", action: nav("/portfolio") }] },
  about: { answer: "FinLit Ventures does investment research, portfolio reviews and financial planning conversations, mostly around Indian stocks, mutual funds and ETFs.", backLabel: "Back to Main Menu",
    options: [{ label: "About FinLit", action: nav("/about") }, { label: "Meet the Founder", action: nav("/about") }] },
  pricing: { answer: `Session prices will be announced soon. Send an enquiry from the services page and we will share the details. The website plans (Basic, Silver, Gold) are separate and are on the Plans page.`, backLabel: "Back to Main Menu",
    options: [{ label: "View Services & Pricing", action: nav("/services") }, { label: "Enquire", action: enq() }] },
  contact: { answer: "Use the contact form and tell us which service you are interested in. We usually reply within one working day.", backLabel: "Back to Main Menu",
    options: [{ label: "Open Contact Form", action: nav("/contact") }, { label: "Explore Services", action: menu("services") }] },
};
