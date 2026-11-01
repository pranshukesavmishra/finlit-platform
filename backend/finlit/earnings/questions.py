"""The ten fixed questions and the prompt that asks them (docs/EARNINGS-CALLS.md, "Questions and prompts").

There is no open chat: a member picks one of these. Every question is asked of ONE earnings-call transcript; the model sees nothing else.
Changing the wording of a question or of the rules bumps PROMPT_VERSION, which makes the nightly job answer again (a validated answer of an
older version is replaced only by a new answer that also passes the checks).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from . import config as C

PROMPT_VERSION = "v1"
NOT_COVERED = "The call did not cover this."
DISCLAIMER = "Information only, not investment advice."
NOTE = "AI-summarised from the transcript. Check the quotes."


@dataclass(frozen=True)
class Question:
    id: str
    label: str              # the chip and the dropdown entry
    title: str              # the label of the answer block ("STRATEGY")
    ask: str                # what to look for, in the model's instructions
    needs_previous: bool = False


QUESTIONS: List[Question] = [
    Question("strategy-moat", "Strategy & moat", "Strategy",
             "What is management's strategy, and what do they say protects the business from competitors (brand, scale, cost, network, licences, customer relationships)?"),
    Question("guidance-outlook", "Guidance & outlook", "Outlook",
             "What does management say about the coming quarters and year: guidance, expected growth, margins, volumes, and the conditions they expect?"),
    Question("margins-costs", "Margins & costs", "Margins",
             "What does management say about margins and costs this quarter: what moved them, input costs, pricing, efficiency, and what they expect next?"),
    Question("demand-orders", "Demand & order book", "Demand",
             "What does management say about demand: order book or pipeline, volumes, customer behaviour, market share, and where demand is strong or weak?"),
    Question("capex-debt", "Capex & debt", "Capex and debt",
             "What does management say about capital spending, expansion plans, borrowings, repayment, leverage and funding?"),
    Question("risks-raised", "Risks raised", "Risks",
             "Which risks, headwinds or uncertainties did management or the company itself mention (regulation, competition, costs, supply, currency, customers)?"),
    Question("management-changes", "Management changes", "Management",
             "Were any changes to the leadership team, board or key people announced or discussed, and any succession or organisation changes?"),
    Question("what-changed", "What changed vs last quarter", "What changed",
             "What is different in this call compared with the previous quarter's call: new topics, changed guidance, changed tone on demand, margins, costs or plans? "
             "Each sentence says whether its quote is from THIS call or the PREVIOUS call.", needs_previous=True),
    Question("capital-allocation", "Dividends & buybacks", "Capital allocation",
             "What does management say about dividends, share buybacks, acquisitions, investments in new businesses and how it uses its cash?"),
    Question("analyst-concerns", "What analysts pushed on", "Analyst questions",
             "On what themes did the analysts on the call press management in their questions (the topics they came back to, and what they were concerned about)?"),
]
BY_ID: Dict[str, Question] = {q.id: q for q in QUESTIONS}

# Words that turn a summary into advice. Checked on every sentence we write (never on a quote: a manager may say "buyback" or "we will sell the unit").
ADVICE_WORDS = ("buy", "sell", "hold", "accumulate", "target", "targets", "recommend", "recommends", "recommended", "recommendation", "overweight", "underweight", "outperform",
                "underperform")
ADVICE_PHRASES = ("we recommend", "price target", "target price", "should invest", "good investment", "worth buying", "avoid the stock")

SYSTEM_RULES = f"""You summarise one Indian listed company's earnings-call transcript for readers who are not experts.
You are given the transcript text (and, for one question, the previous quarter's transcript). Use ONLY those texts. Never use outside knowledge or the internet.

For each question you are asked, return:
  "covered": true if the transcript speaks to the question, false if it does not (then give no sentences);
  "sentences": {C.MIN_SENTENCES}-{C.MAX_SENTENCES} short, plain-English sentences (at most 40 words each). Each sentence has
      "text":   your sentence;
      "quote":  ONE exact, unbroken excerpt copied character for character from the transcript that supports the sentence, between {C.MIN_QUOTE_CHARS} and {C.MAX_QUOTE_CHARS} characters;
      "source": "current" (the quote is from this call) or "previous" (from the previous call; only for the question that asks for it).

Hard rules:
- A quote must appear word for word in the transcript. Do not fix grammar, do not join two places, do not use ellipses. If you cannot quote it, do not say it.
- Report what management or analysts said, with numbers exactly as stated. Do not calculate, estimate or add numbers that are not in the quote.
- Never give advice or a view. Do not use these words in your sentences: buy, sell, hold, accumulate, target, recommend, overweight, underweight, outperform.
  Say "aims" or "plans" instead of "targets"; say "expects" rather than predicting a price or a return.
- No praise or criticism of your own. Attribute statements ("Management said...", "An analyst asked...").
- If the call does not cover a question, set covered to false. That is a correct answer.
- Output JSON only, in exactly this shape, with one entry for every question id you were asked:
  {{"answers": {{"<question id>": {{"covered": true, "sentences": [{{"text": "...", "quote": "...", "source": "current"}}]}}}}}}
"""


def question_block(questions: Sequence[Question]) -> str:
    return "\n".join(f'- id "{q.id}": {q.ask}' for q in questions)


def build_prompt(company: str, label: str, questions: Sequence[Question], transcript: str, previous: Optional[str] = None, previous_label: str = "") -> Dict[str, str]:
    """{'system': ..., 'user': ...} for one request that answers every question in `questions` from one call."""
    parts = [f"Company: {company}", f"This call: {label}", "", "Questions:", question_block(questions), "", f"=== TRANSCRIPT OF THIS CALL ({label}) ===", transcript]
    if previous is not None:
        parts += ["", f"=== TRANSCRIPT OF THE PREVIOUS CALL ({previous_label}) ===", previous]
    parts += ["", "Answer every question above. JSON only."]
    return {"system": SYSTEM_RULES, "user": "\n".join(parts)}


def public_questions(with_previous: bool = True) -> List[dict]:
    return [{"id": q.id, "label": q.label, "title": q.title} for q in QUESTIONS if with_previous or not q.needs_previous]
