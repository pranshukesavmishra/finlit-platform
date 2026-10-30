# Prism classification: industry label to model group

## What went wrong with Coal India (root cause)

FinLit Prism picks one of six model groups (BANK, NBFC, INSURANCE, REALTY, UTILITY, HEAVY, MFG, LIGHT) from the FinEdge profile labels
(`industry`, `sector`, `sub_industry`, `macro_sector`) with the regex rules in `site-api/backend/premium_classification.py`.
Coal India's labels are "Coal" (industry) and "Energy" (sector / macro sector). Neither word matched any rule (`mining|oil|petroleum|refiner|gas|metal|cement|steel`
did not contain "coal" or "energy"), so `resolve_group` returned `("MFG", True)`: "no group, MFG used only to compute inputs".
`premium_data.adapt_inputs` turns that `True` into a rating blocker, so the engine returned NOT RATED with all four part scores withheld. The inputs were
complete (100% found), which is why the card showed "100% of inputs available" beside "NOT RATED".

The card then hid the specific reason: `PrismCompare.tsx` printed a fixed sentence ("Too little verified data to rate this company") whatever the reason,
although the report carried `rating.notRatedReasons[0]` ("... industry label ... not mapped ..."). The Gold header badge shows the Prism rating only, so for a
Gold user "the FinLit score is not coming" is this same NOT RATED. The basic FinLit score (five pillars) has no industry logic at all and was never blocked:
`backend/tests/test_score_extremes.py` scores a debt-free, zero-interest, negative-equity, huge-figure or no-dividend company normally.

The Bajaj Finserv fix (classification version 2) only added financial labels, so Coal and every other label outside the old word list stayed blocked.

## The fix (classification version 3)

* New rules (`NEW_FALLBACK_RULES`) are applied only after every older rule, so **no label that already had a group changed group** (checked label by label against the old rules).
* Trusts and funds are detected first (`unrated_kind`) and stay NOT RATED on purpose, with an honest reason.
* The blocker text is now specific and never says data is missing: `unmapped_reason()`.
* `CLASSIFICATION_VERSION` is 3 in `premium_classification.py` and `backend/finlit/prism.py` (a test keeps them equal), so every stored NOT RATED report blocked
  by the classification check and calculated under an older version is recalculated.

## Label to group

| Labels (any of industry / sector / sub-industry / macro sector) | Group | Why |
|---|---|---|
| Coal, Lignite, Mining & Minerals, Energy Minerals, Oil & Gas (exploration, refining, gas distribution), Petroleum, Aluminium, Copper, Zinc, Ferro alloys, Iron & steel, Metals, Cement, Forgings & castings, Forest products, bare "Energy" | HEAVY | Large fixed assets, commodity cycles, capex-led; Coal India belongs here despite no debt |
| Power generation / transmission / utilities, Renewable energy, Solar, Wind, Hydro, Electricity, Ports, Airports, Roads & highways, Railways, Water, Telecom, Construction, Infrastructure | UTILITY | Regulated or contracted networks, long-life assets, leverage normal |
| Chemicals, Specialty chemicals, Petrochemicals, Agrochemicals, Fertilisers, Dyes & pigments, Polymers, Textiles, Auto & ancillaries, Capital goods, Engineering, Defence, Aerospace, Shipping, Airlines, Logistics, Paper, Sugar, Tobacco, Alcohol (breweries, distilleries), Packaging, Jewellery, Building products, Home furnishings, Diversified, Conglomerates, Healthcare, Hospitals, Diagnostics, Medical equipment | MFG | Plant, inventory and working capital, the default product-business model |
| Software / IT, FMCG, Consumer staples / goods, Household & personal care, Pharma, Media, Broadcasting, Gaming, Education, Trading, Travel & tourism, Retail, Hotels, Courier & air freight, Investment managers, Fund houses | LIGHT | Asset-light, margin and growth led |
| Banks / NBFC / Insurance / Real estate | BANK / NBFC / INSURANCE / REALTY | Unchanged; financial labels are resolved first so "Power Finance" or "Infrastructure Finance" never become UTILITY |
| REIT, InvIT, Business trusts, Investment trusts | none (NOT RATED on purpose) | "Trusts (REITs, InvITs) are not rated by this model, which scores operating companies." |
| ETF, Mutual fund, SPAC, closed-end funds | none (NOT RATED on purpose) | "Funds, ETFs and SPACs are not rated by this model, which scores operating companies." |

Precedence (unchanged): trusts / funds, then INSURANCE, NBFC, BANK, financial LIGHT, generic NBFC, REALTY, UTILITY, HEAVY, LIGHT, recognised manufacturing words, the
older fallbacks, then the new fallbacks. Vehicle manufacturing is never UTILITY. The regression test `site-api/backend/tests/test_premium_label_coverage.py` resolves a list of
business labels plus every industry/sector label recorded in the repository (screener demo, search index, peer groups) and fails if one has no group unless it is listed as intentionally unrated.
A label that is still unmapped in production shows in `audit-prism` with example symbols.

## Recomputing after deploy

The nightly job already runs `precompute-prism --stale-not-rated`; to do it now, on the server:

```
cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml exec -T -d app sh -c 'python -m finlit.worker precompute-prism --stale-not-rated > /tmp/prism-stale.log 2>&1'
```

It recalculates at most 300 reports per run, one second apart; repeat until `audit-prism` shows no "calculated under older rules" line. To see the buckets, labels and example symbols:

```
cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml exec -T -d app sh -c 'python -m finlit.worker audit-prism > /tmp/prism-audit.log 2>&1'
```

then `docker compose ... exec -T app cat /tmp/prism-audit.log`. The basic FinLit score needs no recalculation for this issue (it was never blocked). `score-all` rescoring is only for companies with
no or an old score row.

To verify in a browser: open `/stock/COALINDIA` as a Gold user (the Prism card shows a score and four part scores, not "Not rated"), open `/prism/COALINDIA`, click Recalculate if a stored
report is still old, and check the Quarterly results / screener "Not rated" tooltip reads the new reason for any company still blocked.
