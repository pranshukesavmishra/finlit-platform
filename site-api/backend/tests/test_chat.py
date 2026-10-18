"""Local, provider-mocked checks for the FinLit AI endpoint."""
import asyncio
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend import server


def install_fake_genai(monkeypatch, generate_content):
    fake_types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    fake_genai = SimpleNamespace(
        Client=lambda **kwargs: SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        ),
        types=fake_types,
    )
    google_module = types.ModuleType("google")
    google_module.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)


def request():
    return SimpleNamespace(
        client=SimpleNamespace(host="test-chat-client"),
        headers={},
    )


def test_chat_returns_gemini_response_and_passes_bounded_context(monkeypatch, caplog):
    caplog.set_level("INFO")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()
    captured = {}

    def generate_content(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(text="This is general financial education.")

    install_fake_genai(monkeypatch, generate_content)
    payload = server.ChatRequest(
        message="What was the concept we discussed?",
        history=[
            server.ChatTurn(role="user", content="Explain diversification."),
            server.ChatTurn(role="assistant", content="It spreads exposure."),
        ],
    )
    result = asyncio.run(server.chat(payload, request()))

    assert result.response == "This is general financial education."
    assert captured["model"] == "gemini-3.8-flash"
    assert [turn["role"] for turn in captured["contents"]] == ["user", "model", "user"]
    assert "Avoid greetings, congratulations, filler" in captured["config"]["system_instruction"]
    assert "Do not invent live market data" in captured["config"]["system_instruction"]
    assert "Do not use Markdown tables" in captured["config"]["system_instruction"]
    assert "Premature FD withdrawal" in captured["config"]["system_instruction"]
    assert "Do not quote current savings-account rates" in captured["config"]["system_instruction"]
    assert "model_id=gemini-3.8-flash" in caplog.text
    assert "bounded_history_length=2" in caplog.text


def test_chat_returns_useful_error_when_key_is_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    server._chat_attempts.clear()
    with pytest.raises(HTTPException) as error:
        asyncio.run(server.chat(server.ChatRequest(message="Hello"), request()))
    assert error.value.status_code == 503


def test_chat_hides_provider_error_details_and_logs_safe_diagnostics(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()

    class ProviderError(Exception):
        code = 429

    install_fake_genai(monkeypatch, lambda **kwargs: (_ for _ in ()).throw(ProviderError("secret provider detail")))
    with pytest.raises(HTTPException) as error:
        asyncio.run(server.chat(server.ChatRequest(message="private question"), request()))
    assert error.value.status_code == 502
    assert "secret provider detail" not in error.value.detail
    assert "exception_type=ProviderError" in caplog.text
    assert "provider_status=429" in caplog.text
    assert "model_id=gemini-3.8-flash" in caplog.text
    assert "bounded_history_length=0" in caplog.text
    assert "secret provider detail" not in caplog.text
    assert "private question" not in caplog.text


def test_chat_rate_limit_is_enforced():
    server._chat_attempts.clear()
    for index in range(server.CHAT_MAX_REQUESTS_PER_MINUTE):
        assert not server.chat_rate_limit_exceeded("test", float(index))
    assert server.chat_rate_limit_exceeded("test", 9.5)


def test_chat_rejects_overlong_message():
    with pytest.raises(ValueError):
        server.ChatRequest(message="x" * 2001)


def test_chat_retries_when_gemini_reports_max_tokens(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()
    calls = []
    complete_response = (
        "Saving keeps money accessible. Investing can grow over time, but it carries risk.\n\n"
        + ("Compare your time horizon, liquidity needs, and comfort with market fluctuations. " * 100)
        + "END_OF_COMPLETE_LONG_EXPLANATION"
    )

    def generate_content(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return SimpleNamespace(text="Saving keeps money", candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")])
        return SimpleNamespace(text=complete_response, candidates=[SimpleNamespace(finish_reason="STOP")])

    install_fake_genai(monkeypatch, generate_content)
    result = asyncio.run(server.chat(
        server.ChatRequest(message="Explain saving versus investing with an example."), request()
    ))

    assert result.response == complete_response
    assert result.response.endswith("END_OF_COMPLETE_LONG_EXPLANATION")
    assert [call["config"]["max_output_tokens"] for call in calls] == [700, 1600]
    assert "event=gemini_max_tokens" in caplog.text
    assert "finish_reason=MAX_TOKENS" in caplog.text
    assert "attempt=1" in caplog.text
    assert "output_token_limit=700" in caplog.text
    assert "model_id=gemini-3.8-flash" in caplog.text
    assert "bounded_history_length=0" in caplog.text
    assert "Saving keeps money" not in caplog.text


def test_chat_logs_second_max_tokens_attempt_before_502(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()
    install_fake_genai(
        monkeypatch,
        lambda **kwargs: SimpleNamespace(
            text="partial private response",
            candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
        ),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(server.chat(server.ChatRequest(message="private question"), request()))

    assert error.value.status_code == 502
    assert "event=gemini_max_tokens" in caplog.text
    assert "attempt=2" in caplog.text
    assert "output_token_limit=1600" in caplog.text
    assert "private question" not in caplog.text
    assert "partial private response" not in caplog.text


def test_chat_returns_complete_salary_example_and_follow_up_context(monkeypatch):
    import json

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    server._chat_attempts.clear()
    salary_question = (
        "I'm 24 years old and have just started earning ₹50,000 per month. "
        "Explain the difference between saving and investing using a simple example from my monthly salary."
    )
    salary_answer = (
        "Saving keeps money accessible for near-term needs. Investing puts money into assets that may grow over time, "
        "with a risk of loss.\n\nFor illustration only, imagine ₹35,000 goes to monthly expenses, ₹5,000 to an "
        "easy-access savings goal, and ₹10,000 toward a long-term investment goal. Those figures are an example, "
        "not a recommendation for your budget."
    )
    follow_up_answer = "The savings portion is easier to access; investments can fluctuate in value."
    calls = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        response = salary_answer if len(calls) == 1 else follow_up_answer
        return SimpleNamespace(text=response, candidates=[SimpleNamespace(finish_reason="STOP")])

    install_fake_genai(monkeypatch, generate_content)
    first_result = asyncio.run(server.chat(
        server.ChatRequest(message=salary_question, history=[]), request()
    ))
    first = json.loads(first_result.model_dump_json())
    follow_up_result = asyncio.run(server.chat(
        server.ChatRequest(
            message="Which part is more accessible?",
            history=[
                server.ChatTurn(role="user", content=salary_question),
                server.ChatTurn(role="assistant", content=salary_answer),
            ],
        ),
        request(),
    ))
    follow_up = json.loads(follow_up_result.model_dump_json())

    assert first["response"] == salary_answer
    assert "₹50,000" not in first["response"]  # sample amounts remain illustrative, no forced salary echo
    assert not first["response"].startswith("Please note:")
    assert follow_up["response"] == follow_up_answer
    assert [turn["role"] for turn in calls[1]["contents"]] == ["user", "model", "user"]
