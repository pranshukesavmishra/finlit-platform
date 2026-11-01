"""The knobs of the earnings-call summaries, in one place (docs/EARNINGS-CALLS.md, "Cost and quotas"). Widening coverage is a change to these numbers or an env var."""
from __future__ import annotations

import os
from typing import Mapping, Optional

# ---- coverage: the largest companies by market cap, the latest quarters. Widen with EARNINGS_TOP_COMPANIES / EARNINGS_QUARTERS.
TOP_COMPANIES = 300
LATEST_QUARTERS = 2

# ---- per run bounds (one nightly run does at most this much, then stops; the next run resumes)
MAX_CALLS_PER_RUN = 25               # calls (transcripts) summarised in one run
MAX_DOWNLOADS_PER_RUN = 40           # transcript PDFs downloaded in one run
REQUEST_BUDGET_PER_RUN = 120         # all outbound requests to the exchanges in one run (announcement lookups and PDFs together)
NSE_LOOKUPS_PER_RUN = 60             # announcement lookups against the exchange for companies the stored feed does not cover

# ---- the free LLM tier: one request answers every question of one call. The numbers are kept below the published free limits.
LLM_REQUESTS_PER_MINUTE = 6
LLM_REQUESTS_PER_DAY = 120
LLM_BACKOFF_SECONDS = (20, 60, 180)  # waits after a 429 (a longer Retry-After from the provider wins)
MAX_TRANSCRIPT_CHARS = 350_000       # a longer transcript is cut here (the text sent, and the text quotes are checked against, is the same)
MAX_PREVIOUS_CHARS = 150_000         # the previous quarter's call, for "what changed"
MAX_PDF_BYTES = 15 * 1024 * 1024
MIN_TEXT_CHARS = 8_000               # less text than this is a scan or a cover note, not a transcript
MAX_DOWNLOAD_ATTEMPTS = 4
RETRY_FAILED_AFTER_DAYS = 2

# ---- the answer
MIN_SENTENCES, MAX_SENTENCES = 2, 6
MIN_QUOTE_CHARS, MAX_QUOTE_CHARS = 25, 400
MAX_SENTENCE_CHARS = 300
MAX_ANSWER_ATTEMPTS = 3              # a question that keeps failing validation is left alone after this many runs (until the prompt version changes)

# ---- members
CALLS_PER_MONTH_GOLD = 5             # mirrored in auth/entitlements.LIMITS["gold"]["earnings_calls_per_month"]


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return max(0, int(env.get(name, default)))
    except (TypeError, ValueError):
        return default


def top_companies(env: Optional[Mapping[str, str]] = None) -> int:
    return _int(os.environ if env is None else env, "EARNINGS_TOP_COMPANIES", TOP_COMPANIES)


def latest_quarters(env: Optional[Mapping[str, str]] = None) -> int:
    return max(1, _int(os.environ if env is None else env, "EARNINGS_QUARTERS", LATEST_QUARTERS))


def llm_per_day(env: Optional[Mapping[str, str]] = None) -> int:
    return _int(os.environ if env is None else env, "EARNINGS_LLM_PER_DAY", LLM_REQUESTS_PER_DAY)


def llm_per_minute(env: Optional[Mapping[str, str]] = None) -> int:
    return max(1, _int(os.environ if env is None else env, "EARNINGS_LLM_PER_MINUTE", LLM_REQUESTS_PER_MINUTE))
