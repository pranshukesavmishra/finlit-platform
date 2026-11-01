"""Mutual Fund Screener (docs/MF-FILTERS.md).

  spec.py    the filter registry (every numeric field with its SQL and histogram edges, every whitelist), parsing of the query string into validated
             predicates, and the WHERE builder. Pure: no database, no import of finlit.mf (so mf.py can use it).
  facets.py  the one-call answer of /api/mf/filters?screen=1: counts per option, histograms, "N of M have this figure", the return-vs-risk scatter.
  job.py     the nightly `refresh-mf-screen` job that fills mf_screen, mf_screen_hold, mf_cat_flow and the tags.
  calc.py    the pure figures of that job (volatility, worst month, downside capture, ranks ...), unit tested on their own.

Information only: every figure is a plain description of past data. Nothing here ranks funds by quality or says what to do."""
