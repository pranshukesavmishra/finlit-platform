"""The knobs of the company brief job, in one place (docs/COMPANY-BRIEF.md, "Cost"). Each can be changed with an environment variable, never with a code change."""
from __future__ import annotations

import os
from typing import Mapping

MAX_WRITES_PER_RUN = 6            # briefs (or parts) written by the model in one run: the nightly cost cap. BRIEF_MAX_WRITES_PER_NIGHT
MAX_TOKENS_OUT = 16384            # the longest brief the model may return
LLM_REQUESTS_PER_MINUTE = 4       # BRIEF_LLM_PER_MINUTE
LLM_REQUESTS_PER_DAY = 60         # BRIEF_LLM_PER_DAY: shared across runs through Redis
MAX_DOCS_PER_BRIEF = 8            # PDFs read for one brief
MAX_PDF_BYTES = 40 * 1024 * 1024  # an annual report is large
MAX_PAGES = 700
REQUEST_BUDGET_PER_RUN = 120      # all outbound requests (PDFs and robots.txt) in one run
SOURCE_WINDOW_DAYS = 200          # filings older than this are not read for a first brief (the annual report is read whatever its date)
MAX_ATTEMPTS = 3                  # a company whose output keeps failing the gates is left alone after this many tries on the same filings
RETRY_AFTER_HOURS = 24
PROMPT_VERSION = "brief-1"


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    try:
        return max(0, int(env.get(name, default)))
    except (TypeError, ValueError):
        return default


def max_writes(env: Mapping[str, str] = os.environ) -> int:
    return _int(env, "BRIEF_MAX_WRITES_PER_NIGHT", MAX_WRITES_PER_RUN)


def llm_per_minute(env: Mapping[str, str] = os.environ) -> int:
    return max(1, _int(env, "BRIEF_LLM_PER_MINUTE", LLM_REQUESTS_PER_MINUTE))


def llm_per_day(env: Mapping[str, str] = os.environ) -> int:
    return _int(env, "BRIEF_LLM_PER_DAY", LLM_REQUESTS_PER_DAY)
