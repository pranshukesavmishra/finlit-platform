# Profit and revenue outlook (Gold)

`POST /api/outlook/{symbol}` with `{kind: "profit"|"revenue", horizon: "short"|"mid"|"long", weights?: {parameter key: percent}, normalise?: bool, statement?}`.
Code: `backend/finlit/outlook/` (`model.py` the model, `sector.py` peer values, `inputs.py` stored report shape, `backtest.py` validation harness, `router.py` the API).
Information only, not investment advice. Estimates from the company's own history and its sector, not a prediction. The weights are starting values and have not yet been validated.
Method, data rules and what was adapted: [outlook/METHOD.md](outlook/METHOD.md). Back-test: [outlook/BACKTEST.md](outlook/BACKTEST.md).

## Contract
- Gold (and administrators) only; other plans get 403 `plan_required`. Responses are `private, no-store`; cached 10 minutes in Redis by symbol, statement, kind, horizon, weights hash and the stored report version.
- `weights` omitted = "Use our model" (the horizon's column). Otherwise every parameter of the kind, each 0-100, total 100 within 0.01 (else 422 `invalid_weights`), or `normalise: true` to scale them to 100.
- Response: `horizon`, `weights`, `defaultWeights`, `rate {ratePct, rows[] {label, weightPct, effectiveWeightPct, valuePct, rawPct, capped, contributionPts, status, method, reason}, unavailable, weightLeftPct}`, `forecast {available, reason, base, years[], rule}`, `history {points[] {period, valueCr, reportedCr, adjusted}}`, `adjustedYears`, `asOf`, `disclaimer`.
- The chart, the "how this is built" table and the year table on `/outlook/:symbol` are all drawn from this one response.

## Page
Two annual line charts (revenue, profit) above the tables: reported years solid with filled dots, estimate years dashed with hollow dots joined at the latest reported year, a "Forecast starts FYxx" divider, tooltip and arrow-key reading, "Show as table", CSV download. With custom weights the model's estimate is a second dashed line. No range band is drawn: the model gives one rate, not a range.
The earlier outlook score, group scores and four-quarter range were replaced by this model (see git history).
