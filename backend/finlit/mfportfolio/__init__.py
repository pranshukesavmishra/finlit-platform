"""My mutual funds: a member's own mutual fund holdings, valued with the latest NAV, with the fund's Health Score (Gold) and returns.

Package layout
  parse   numbers, dates, folios and one imported row -> a clean row, or the reason it cannot be used (pure)
  match   a row -> a scheme: AMFI code, ISIN, exact normalised name, then a conservative fuzzy match that only ever suggests (pure, over an Index)
  calc    lots + NAV -> invested, current value, gain, XIRR; the summary, the allocation and the plain-words concentration note (pure)
  api     /api/me/mf-portfolio: list, add, update, delete, import-preview, import-commit

Everything is descriptive. No buy, sell, hold, switch or redeem wording anywhere. Information only, not investment advice.
"""

DISCLAIMER = "Information only, not investment advice."
SCORE_DISCLAIMER = "Describes the fund's health from its past NAVs, costs and holdings; not a recommendation."
