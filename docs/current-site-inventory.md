# finlitventures.com today: what must be rebuilt

Source: `Yusra-Khan532/Financial-Portfolio` at commit `6023c0d` (11 Oct 2026). React (CRA) frontend on Vercel,
FastAPI + MongoDB backend. This is the migration checklist: every row needs a home in `finlit-platform`.

## Pages

| Today | What it does | New platform |
|---|---|---|
| `/` | Hero (founder Nishant Jain: IIT Kanpur, CFA L1, NISM RA), realised portfolio performance, 7-step process, philosophy marquee, testimonial, contact form | Home, same story, live data |
| `/services` | 5 services; pricing: First session ₹99, 1 month ₹299, 3 months ₹699, 6 months ₹1,299, 1 year ₹2,499 (per service); enquiry dialog | Services + enquiry, prices from one server table |
| `/why-we-exist` | Market-size pitch (TAM funnel, tiers, who we help, growth loop) | Why we exist |
| `/about` | Pillars, principles, founder profile | About |
| `/contact` | Contact form, email, LinkedIn | Contact |
| `/portfolio` | Realised P&L report from an Upstox PDF: KPIs, monthly/cumulative P&L, attribution, outcomes, charges | Portfolio report (PDFs stored in R2, not local disk) |
| `/financial-product` | "Coming soon" placeholder | Replaced by Research (stock reports) + Plans |
| `/blog`, `/blog/:slug` | Research CMS: articles (sanitised HTML), PDFs, spreadsheets, images | Blog in Postgres, files in R2 |
| `/blog/admin/*` | Single env-var admin; JWT in sessionStorage; CMS editor (TipTap), portfolio PDF upload, stock dashboard | Admin area on real accounts (passkey-required admin role) |
| — | No legal pages | Terms, Privacy, Research disclosures (new) |

Global elements: NIFTY 50 market ticker (Upstox LTP, 60 s), FinLit Assistant chat (guided menu + Gemini free-text),
theme toggle, footer disclaimer ("technology company, not registered with SEBI or AMFI").

## Backend features to carry over

- **Content:** list/detail published content; admin CRUD with nh3 sanitising; slug uniqueness; uploads
  (pdf/xlsx/xls/csv/png/jpg/webp, 15 MB, MIME + signature checks); assets served only when published.
- **Portfolio:** Upstox realised-P&L PDF parser (pypdf + regex): period, gross/net P&L, charges, trades;
  metrics and charts; one current report.
- **Leads:** `/contact` (8/hour/IP) and `/service-enquiry`, saved then emailed to the owner via Resend;
  auto-reply exists but is off.
- **Chat:** Gemini, 10/min/IP, system prompt lists services and the ₹99 first session.
- **Market ticker:** NIFTY 50 constituents (niftyindices CSV, cached 6 h) + Upstox LTP.

## Known gaps fixed by the rebuild

- Files on local disk (lost on serverless; the "View full P&L report" link can break): **R2**.
- Rate limits and caches in process memory: **Redis**.
- Services list duplicated in 3 places: **one server table**.
- Admin JWT in sessionStorage, no revocation, single shared admin: **real accounts, sessions, roles**.
- No admin view for leads: **admin leads inbox**.
- No legal pages or per-page SEO: **legal pages, per-route titles and descriptions**.
- Blog "Research" filter returns everything: **fixed**.
- Brand naming inconsistent ("Nishant Jain PMS API", "FinLitventure"): **FinLit Ventures everywhere**.

## Brand assets

- Logo: `frontend/src/assets/brand/finlit-logo-transparent.png` (930×610, only logo file).
- Favicon: `frontend/public/favicon.svg` ("FL" monogram, navy #050E1D, gold #E7C56B).
- Founder photo: `frontend/src/assets/team/nishant.png`.
- Contact: finlit.start@gmail.com (company email to replace it later); LinkedIn company page.
