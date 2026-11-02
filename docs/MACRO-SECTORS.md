# Macro backdrop per sector

Spec: "From macro data to sector signals" (owner, 1 Nov 2026). Code: `backend/finlit/macro_sectors.py`, route `GET /api/macro/sectors[?symbol=]`,
pages: Macro page "Sector impact" panel (`frontend/src/components/MacroSectorImpact.tsx`) and the "Macro backdrop" line under a company's tags (`stock/MacroBackdrop.tsx`).

* Inputs: the macro page's stored payload (MoSPI and RBI: CPI, WPI, repo and real repo rate, GDP, IIP, bank credit and deposits, rupee, food CPI, unemployment)
  and Brent from `commodity_snapshots` (3-month change). A missing input is left out with its reason, never read as zero.
* Method, exactly as the spec: signal = average of level and momentum, each capped at +-1; raw = sum of sensitivity x signal; score = 50 + 50 tanh(raw / 3).
  Labels 70+ strong tailwind, 58-69 tailwind, 43-57 neutral, 31-42 headwind, 30 or less strong headwind. Reasons: the two largest contributions of 0.3 or more.
  `tests/test_macro_sectors.py` reproduces the spec's page-4 table (all 18 sectors) and its crude example (page 5).
* A company's sector comes from its industry words (`sector_for`); a company outside the 18 sectors shows the reason instead of a score.
* Plan and switch: Gold, enforced by the server. Off for members until switched on in Console > Data health > Feature switches ("Macro backdrop per sector");
  administrators always see it, marked "Preview", so it can be reviewed first. The spec asks for a legal check before members see it.
* Not done (needs data): the 10-year backtest of the sensitivities (sector index history), and the company-level exposure scaling of the spec's page 7.
