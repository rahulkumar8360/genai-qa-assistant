# Checks the exact request sent to the Anthropic API and how each kind of
# response is read back - using a fake client, so no key and no network.

from types import SimpleNamespace

import config
from qa.llm import ClaudeBackend, make_backend
from qa.prompts import build_request


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(content, stop_reason="end_turn"):
    response = SimpleNamespace(
        content=content, stop_reason=stop_reason, model="claude-opus-5",
        usage=SimpleNamespace(input_tokens=900, output_tokens=40),
    )
    messages = FakeMessages(response)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def text_block(text):
    return SimpleNamespace(type="text", text=text)


REQUEST = build_request("How long must passwords be?",
                        [{"source": "it.md", "section": "Passwords", "page": 1,
                          "text": "Passwords must be at least 14 characters long."}], version="v3")


def test_request_shape():
    client, messages = fake_client([text_block("At least 14 characters [1].")])
    ClaudeBackend(client=client).generate(REQUEST)

    call = messages.calls[0]
    assert call["model"] == config.MODEL
    assert call["system"] == REQUEST["system"]
    assert call["messages"] == REQUEST["messages"]
    assert call["output_config"] == {"effort": config.EFFORT}
    assert call["fallbacks"] == [{"model": config.FALLBACK_MODEL}]
    assert "server-side-fallback-2026-06-01" in call["betas"]
    # removed on this model family - sending it would be a 400
    assert "temperature" not in call
    assert "thinking" not in call or call["thinking"].get("type") == "adaptive"


def test_thinking_blocks_are_not_part_of_the_answer():
    thinking = SimpleNamespace(type="thinking", thinking="")
    client, _ = fake_client([thinking, text_block("At least 14 characters [1].")])
    out = ClaudeBackend(client=client).generate(REQUEST)
    assert out["text"] == "At least 14 characters [1]."
    assert out["usage"] == {"input_tokens": 900, "output_tokens": 40}


def test_refusal_is_reported_not_read_as_text():
    client, _ = fake_client([], stop_reason="refusal")
    out = ClaudeBackend(client=client).generate(REQUEST)
    assert out["stop_reason"] == "refusal"
    assert "declined" in out["text"]


def test_truncated_answer_is_marked():
    client, _ = fake_client([text_block("Passwords must be")], stop_reason="max_tokens")
    out = ClaudeBackend(client=client).generate(REQUEST)
    assert "cut off" in out["text"]


def test_auto_backend_without_key_is_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert make_backend("auto").name == "offline"
