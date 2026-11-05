"""The FinLit AI chat and the question bank: a recognised question reaches the assistant as an instruction, small talk does not, and a problem in the bank never breaks the chat."""
import asyncio
from types import SimpleNamespace

from backend import question_matcher, server
from backend.tests.test_chat import install_fake_genai, request


def ask(monkeypatch, message):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()
    seen = {}

    def generate_content(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(text="An answer.")

    install_fake_genai(monkeypatch, generate_content)
    result = asyncio.run(server.chat(server.ChatRequest(message=message, history=[]), request()))
    return result, seen["config"]["system_instruction"]


def test_a_concept_question_from_the_bank_reaches_the_assistant_as_an_instruction(monkeypatch):
    result, system = ask(monkeypatch, "what is free float")
    assert result.question_id == "F.1.1.1" and result.response == "An answer."
    assert "FinLit question bank" in system and "What is free float?" in system and "cover every part" in system
    assert "up to 170 words" in system


def test_a_company_question_is_recognised_but_gets_no_instruction_without_the_data_tools(monkeypatch):
    """The instruction tells the assistant to use the data tools; with none attached it must not be asked to produce a company's figures from memory."""
    result, system = ask(monkeypatch, "what are the current PE, PB and P/S ratios of TCS")
    assert result.question_id == "C.6.1.1"
    assert "FinLit question bank" not in system


def test_small_talk_and_unrelated_questions_are_untouched(monkeypatch):
    for msg in ("hello", "tell me a joke", "what is the weather in Mumbai today"):
        result, system = ask(monkeypatch, msg)
        assert result.question_id is None and "FinLit question bank" not in system and result.response == "An answer."


def test_a_problem_in_the_bank_never_breaks_the_chat(monkeypatch):
    def boom():
        raise RuntimeError("bank file missing")
    monkeypatch.setattr(question_matcher, "bank", boom)
    result, system = ask(monkeypatch, "what is EBITDA")
    assert result.response == "An answer." and result.question_id is None and "FinLit question bank" not in system


def test_a_company40_question_reaches_the_assistant_with_its_plan_and_its_data_limits(monkeypatch):
    """With the data tools attached, the data-limited question carries the strict rule: the assistant says what the tools cannot give and never fills the gap."""
    from backend import mcp_tools
    from backend.tests.test_chat_tools import FakeGemini, FakeMcp, ok_result, QUOTE, says, use_mcp
    mcp_tools.reset_cache()
    use_mcp(monkeypatch, FakeMcp(results={"get_stock_quote": ok_result(QUOTE)}))
    gem = FakeGemini(lambda n, kw: says("The current PE is available; the history is not."))
    gem.install(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()
    result = asyncio.run(server.chat(server.ChatRequest(message="How does the PE of Infosys compare with its own 3-year, 5-year and 10-year average, and in what percentile of its history is it?"), request()))
    system = gem.calls[0]["config"]["system_instruction"]
    mcp_tools.reset_cache()
    assert result.question_id == "C.6.Q23"
    assert "Answer plan:" in system and "DATA LIMITS (strict)" in system and "Never estimate" in system and "10-year average PE" in system
