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
  { n: "01", name: "0 → 1 Investing", icon: "sprout", proposition: "Start investing from zero, with confidence.",
    desc: "We help you understand stocks, ETFs, mutual funds and other investment options to build a strategy aligned with your goals and risk profile." },
  { n: "02", name: "Wealth Planning", icon: "growth", proposition: "Turn your income and savings into long-term wealth.",
    desc: "We create personalized strategies to grow, diversify and protect your wealth across different life stages." },
  { n: "03", name: "Family Financial Planning", icon: "users", proposition: "Plan for what matters most.",
    desc: "From your children's education to major life goals and financial security, we bring your family's goals, investments, insurance and future needs into one clear financial roadmap." },
  { n: "04", name: "Global Investing", icon: "map", proposition: "Look beyond borders to diversify your wealth.",
    desc: "We help you understand and access global investment opportunities while aligning them with your overall portfolio and risk appetite." },
  { n: "05", name: "Portfolio Review & Stock Selection", icon: "gauge", proposition: "Already investing? Get an objective view of your portfolio.",
    desc: "We evaluate diversification, risk, performance and individual holdings to help you make smarter, more informed investment decisions." },
] as const;
export type ServiceName = (typeof SERVICES)[number]["name"];

export const PRICING = [
  { plan: "First Session", price: "₹99", note: "A one-time conversation to understand your goals" },
  { plan: "1 Month", price: "₹299", note: "" },
  { plan: "3 Months", price: "₹699", note: "" },
  { plan: "6 Months", price: "₹1,299", note: "" },
  { plan: "1 Year", price: "₹2,499", note: "Best value" },
];

export const FOUNDER = {
  name: "Nishant Jain",
  role: "Independent Equity Investor & Researcher",
  credentials: ["B.Tech, IIT Kanpur", "Minor in Finance, IIT Kanpur", "CFA Level I Cleared", "NISM Certified Research Analyst"],
  bio: "Nishant’s investment approach is rooted in fundamental research, business quality, valuation discipline, margin of safety, thoughtful position sizing and long-term compounding.",
  linkedin: "https://www.linkedin.com/in/nishant-jain-1464071ab/",
  photo: `${import.meta.env.BASE_URL}team/nishant.webp`,
};

export const PILLARS = [
  { title: "Research", icon: "notes", text: "Fundamental, sectoral and company-level analysis built around business quality, valuation and long-term opportunity." },
  { title: "Portfolio Thinking", icon: "layers", text: "A disciplined view of conviction, allocation, diversification, risk and long-term portfolio construction." },
  { title: "Investor Understanding", icon: "users", text: "Helping investors better understand businesses, markets, portfolio decisions and the reasoning behind investment choices." },
  { title: "Global Perspective", icon: "map", text: "Exploring domestic and international opportunities, including equities, ETFs and broader market exposure." },
];

export const PRINCIPLES = [
  { title: "Independent Thinking", text: "Research before consensus." },
  { title: "Clarity Over Complexity", text: "Investment reasoning should be understandable, structured and evidence-led." },
  { title: "Discipline Over Noise", text: "Process, risk management and long-term thinking matter more than short-term market excitement." },
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
  kpis: [
    { value: 144, prefix: "", suffix: "cr", label: "India's population", source: "Govt. est. 2026" },
    { value: 39, prefix: "", suffix: "cr", label: "Financially literate", source: "NCFE 2026" },
    { value: 12.5, prefix: "~", suffix: "cr", label: "Investing, portfolios under ₹30L", source: "NSE · AMFI 2026" },
    { value: 38.5, prefix: "~", suffix: "cr", label: "Addressable audience", source: "FinLit estimate", gold: true },
  ],
  people: [
    { n: "01", title: "Scattered", text: "Random SIPs, no plan.", icon: "layers" },
    { n: "02", title: "Stuck at Zero", text: "Ready, doesn't know how.", icon: "sprout" },
    { n: "03", title: "Unstructured", text: "Earning well, no goals.", icon: "tag" },
  ],
  suite: [
    { n: "01", title: "Research", text: "A clearer frame for the questions worth asking." },
    { n: "02", title: "Portfolio Reviews", text: "See how your investments work together." },
    { n: "03", title: "Financial Planning", text: "Connect financial decisions to life goals." },
    { n: "04", title: "Wealth Planning", text: "Evolve a long-term plan as life changes." },
  ],
  loop: ["Discover", "Diagnose", "Learn", "Act", "Review", "Upgrade"],
  principles: [
    { title: "Goals before products", text: "Start with what the money needs to accomplish." },
    { title: "Portfolio before individual picks", text: "Evaluate how investments work together." },
    { title: "Review before reaction", text: "Let the plan evolve deliberately instead of reacting to noise." },
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
    greeting: "Welcome to FinLit AI.\nExplore investing, financial planning, and market concepts with clarity.",
    prompt: "How can I help you today?",
    options: [
      { label: "Explore Services", action: menu("services") }, { label: "Portfolio Review", action: menu("portfolio-review") },
      { label: "Financial Planning", action: menu("financial-planning") }, { label: "Global Investing", action: menu("global-investing") },
    ],
    additionalOptions: [
      { label: "Performance", action: menu("performance") }, { label: "About FinLit", action: menu("about") },
      { label: "Pricing & Consultation", action: menu("pricing") }, { label: "Contact the Team", action: menu("contact") },
    ],
  },
  "financial-planning": { answer: "FinLit’s financial planning services include Wealth Planning and Family Financial Planning. Choose a topic to explore what each covers.", backLabel: "Back to Main Menu",
    options: [{ label: "Wealth Planning", action: menu("wealth-planning") }, { label: "Family Financial Planning", action: menu("family-planning") }] },
  services: { answer: "FinLit Ventures offers structured investing and financial planning services designed around different stages of an investor’s journey.", backLabel: "Back to Main Menu",
    options: [{ label: "0→1 Investing", action: menu("zero-to-one") }, { label: "Wealth Planning", action: menu("wealth-planning") }, { label: "Family Financial Planning", action: menu("family-planning") }, { label: "Global Investing", action: menu("global-service") }, { label: "Portfolio Review & Stock Selection", action: menu("portfolio-service") }] },
  "zero-to-one": { answer: "0→1 Investing is designed for individuals who want to start investing with greater clarity and structure. The focus is on understanding goals, risk profile, capital allocation, and building a disciplined investment approach.", backLabel: "Back to Services",
    options: [{ label: "View Services", action: nav("/services") }, { label: "Enquire About This Service", action: enq("0 → 1 Investing") }] },
  "wealth-planning": { answer: "Wealth Planning focuses on aligning investments with long-term financial goals, capital requirements, risk preferences, and overall portfolio structure.", backLabel: "Back to Services",
    options: [{ label: "View Services", action: nav("/services") }, { label: "Enquire", action: enq("Wealth Planning") }] },
  "family-planning": { answer: "Family Financial Planning helps structure financial decisions across family goals such as wealth creation, major expenses, long-term planning, and portfolio organization.", backLabel: "Back to Services",
    options: [{ label: "View Services", action: nav("/services") }, { label: "Enquire", action: enq("Family Financial Planning") }] },
  "global-investing": { answer: "Global Investing helps investors understand opportunities beyond domestic markets and evaluate international exposure as part of a broader portfolio strategy.", backLabel: "Back to Main Menu",
    options: [{ label: "View Global Investing Service", action: nav("/services") }, { label: "Enquire", action: enq("Global Investing") }] },
  "global-service": { answer: "Global Investing helps investors understand opportunities beyond domestic markets and evaluate international exposure as part of a broader portfolio strategy.", backLabel: "Back to Services",
    options: [{ label: "View Global Investing Service", action: nav("/services") }, { label: "Enquire", action: enq("Global Investing") }] },
  "portfolio-service": { answer: "Portfolio Review & Stock Selection focuses on reviewing an existing portfolio, understanding its composition, identifying areas that may require attention, and supporting research-driven stock selection.", backLabel: "Back to Services",
    options: [{ label: "View Portfolio", action: nav("/portfolio") }, { label: "Enquire About Portfolio Review", action: enq("Portfolio Review & Stock Selection") }] },
  "portfolio-review": { answer: "FinLit can help review an existing portfolio from a structured research and portfolio-construction perspective. The review may cover portfolio composition, concentration, allocation, and the reasoning behind holdings.", backLabel: "Back to Main Menu",
    options: [{ label: "View Portfolio", action: nav("/portfolio") }, { label: "Explore Portfolio Review Service", action: menu("portfolio-service") }, { label: "Enquire", action: enq("Portfolio Review & Stock Selection") }] },
  performance: { answer: "You can review FinLit’s latest reported portfolio performance, realised P&L, ROI, win rate, holding period, realised trades, and supporting portfolio analytics on the Portfolio page.", backLabel: "Back to Main Menu",
    options: [{ label: "View Performance", action: nav("/portfolio") }] },
  about: { answer: "FinLit Ventures focuses on investment research, portfolio reviews, financial planning, and structured discussions around Indian equities, mutual funds, ETFs, and global investing.", backLabel: "Back to Main Menu",
    options: [{ label: "About FinLit", action: nav("/about") }, { label: "Meet the Founder", action: nav("/about") }] },
  pricing: { answer: `FinLit’s published engagement options start with ${PRICING[0].plan} at ${PRICING[0].price}. The services page lists the current options and prices.`, backLabel: "Back to Main Menu",
    options: [{ label: "View Services & Pricing", action: nav("/services") }, { label: "Enquire", action: enq() }] },
  contact: { answer: "You can reach the FinLit team through the website contact form. Share the service you’re interested in and the team can follow up with you.", backLabel: "Back to Main Menu",
    options: [{ label: "Open Contact Form", action: nav("/contact") }, { label: "Explore Services", action: menu("services") }] },
};
