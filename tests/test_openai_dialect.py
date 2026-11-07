"""요청 형식·사용량 정리·거절 오류(명세 §24.3, LLD §22.2 B). 네트워크 없이 httpx를 바꿔 끼운다."""

from __future__ import annotations

import json

import httpx
import pytest

from character_factory_poc.common.errors import FactoryError, ProviderRequestError
from character_factory_poc.providers import openai_compat
from character_factory_poc.providers.base import ChatRequest, Message, VisionRequest
from character_factory_poc.providers.openai_compat import (
    OpenAICompatTextModel,
    OpenAICompatVisionModel,
    normalize_usage,
    request_dialect,
)

OPENAI = "https://api.openai.com/v1"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"
RELAY = "http://127.0.0.1:10100/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def chat(response_json: bool = True) -> ChatRequest:
    return ChatRequest(
        "AGENT",
        "s7",
        (Message("system", "규칙"), Message("user", "말투를 정한다")),
        "cf-x/tr1",
        max_output_tokens=1234,
        temperature=0.4,
        response_json=response_json,
    )


def ok(content: str = "{}", usage: dict | None = None, finish: str = "stop") -> httpx.Response:
    data: dict = {
        "model": "m",
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
    }
    if usage is not None:
        data["usage"] = usage
    return httpx.Response(200, json=data)


@pytest.fixture
def capture(monkeypatch):
    """httpx.Client.post를 가짜 응답 목록으로 바꾸고 보낸 본문을 모은다. 대기는 기록만 한다."""
    sent: list[dict] = []
    sleeps: list[float] = []
    replies: list[httpx.Response] = []

    def post(client, url, **kw):
        sent.append({"url": url, **kw})
        return replies.pop(0) if replies else ok()

    monkeypatch.setattr(httpx.Client, "post", post)
    monkeypatch.setattr(openai_compat.time, "sleep", sleeps.append)
    return sent, sleeps, replies


@pytest.mark.parametrize(
    ("url", "dialect"),
    [
        (OPENAI, "openai"),
        ("https://API.OpenAI.com/v1/", "openai"),
        (GEMINI, "gemini"),
        (RELAY, "generic"),
        ("https://test.invalid/v1", "generic"),
        ("https://api.openai.com.evil.invalid/v1", "generic"),
    ],
)
def test_request_dialect_uses_host(url, dialect):
    assert request_dialect(url) == dialect


@pytest.mark.parametrize("effort", ["high", "low", None])
def test_openai_with_reasoning_drops_temperature(capture, effort):
    # 추론 강도를 지정하지 않아도(None) 모델 기본 추론이 켜지므로 temperature를 뺀다.
    sent, _, _ = capture
    OpenAICompatTextModel(OPENAI, "gpt-6.1-sol", reasoning_effort=effort).complete(chat())
    body = sent[0]["json"]
    assert sent[0]["url"] == f"{OPENAI}/chat/completions"
    assert body["max_completion_tokens"] == 1234
    assert "max_tokens" not in body and "temperature" not in body
    assert body.get("reasoning_effort") == effort
    assert ("reasoning_effort" in body) is (effort is not None)
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"][-1]["content"].endswith("(응답 형식: json)")


def test_openai_reasoning_none_keeps_temperature(capture):
    sent, _, _ = capture
    model = OpenAICompatTextModel(OPENAI, "gpt-6.1-terra", reasoning_effort="none")
    model.complete(chat(False))
    body = sent[0]["json"]
    assert body["max_completion_tokens"] == 1234 and "max_tokens" not in body
    assert body["temperature"] == 0.4 and body["reasoning_effort"] == "none"
    assert "response_format" not in body


@pytest.mark.parametrize("model", ["gpt-6.1-sol", "gpt-6.1-sol-2026-10-01", "openai/gpt-6.1-sol"])
def test_openai_sol_rejects_reasoning_none_before_call(capture, model):
    sent, _, _ = capture
    with pytest.raises(ValueError, match="none"):
        OpenAICompatTextModel(OPENAI, model, reasoning_effort="none").complete(chat())
    assert sent == []


@pytest.mark.parametrize("url", [GEMINI, RELAY])
def test_sol_reasoning_none_check_is_openai_only(capture, url):
    # 중계·Gemini 주소는 지금 본문을 그대로 보낸다. 공식 OpenAI 형식에서만 막는다.
    sent, _, _ = capture
    OpenAICompatTextModel(url, "gpt-6.1-sol", reasoning_effort="none").complete(chat())
    assert sent[0]["json"]["temperature"] == 0.4


def test_gemini_keeps_current_arguments(capture):
    sent, _, _ = capture
    model = OpenAICompatTextModel(GEMINI, "gemini-3.8-flash", reasoning_effort="high")
    model.complete(chat())
    body = sent[0]["json"]
    assert body["max_tokens"] == 1234 and "max_completion_tokens" not in body
    assert body["temperature"] == 0.4 and body["reasoning_effort"] == "high"


def test_generic_relay_body_is_unchanged(capture):
    sent, _, _ = capture
    model = OpenAICompatTextModel(
        RELAY, "google-antigravity/gemini-3.8-flash", reasoning_effort="high"
    )
    model.complete(chat())
    assert sent[0]["json"] == {
        "model": "google-antigravity/gemini-3.8-flash",
        "messages": [
            {"role": "system", "content": "규칙"},
            {"role": "user", "content": "말투를 정한다\n\n(응답 형식: json)"},
        ],
        "max_tokens": 1234,
        "temperature": 0.4,
        "reasoning_effort": "high",
        "response_format": {"type": "json_object"},
    }
    assert list(sent[0]["json"]) == [
        "model",
        "messages",
        "max_tokens",
        "temperature",
        "reasoning_effort",
        "response_format",
    ]


@pytest.mark.parametrize(
    ("url", "limit"),
    [(OPENAI, "max_completion_tokens"), (GEMINI, "max_tokens"), (RELAY, "max_tokens")],
)
def test_vision_body_follows_dialect(tmp_path, url, limit):
    image = tmp_path / "a.png"
    image.write_bytes(PNG)
    model = OpenAICompatVisionModel(url, "judge")
    body = model.body(VisionRequest("s4", "cf-x/f1#qa", "판정", (("a", str(image)),), "rules", 777))
    assert body[limit] == 777
    assert ("max_tokens" in body) is (limit == "max_tokens")
    assert ("max_completion_tokens" in body) is (limit == "max_completion_tokens")
    # OpenAI 형식은 모델 기본 추론이 켜지므로 temperature를 빼고, 그 밖은 0을 유지한다.
    if url == OPENAI:
        assert "temperature" not in body
    else:
        assert body["temperature"] == 0
    assert "reasoning_effort" not in body
    assert body["response_format"] == {"type": "json_object"}


def test_vision_result_carries_usage(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(PNG)
    usage = {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 80}

    def handler(req):
        return httpx.Response(
            200, json={"model": "j", "choices": [{"message": {"content": "{}"}}], "usage": usage}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAICompatVisionModel(GEMINI, "judge", client=client).judge(
            VisionRequest("s4", "cf-x/f1#qa", "판정", (("a", str(image)),))
        )
    assert result.input_tokens == 50 and result.output_tokens == 30
    assert result.usage["usageSource"] == "total_minus_prompt"


def test_normalize_usage_openai_details():
    data = {
        "choices": [{"finish_reason": "length"}],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 400,
            "total_tokens": 1400,
            "prompt_tokens_details": {"cached_tokens": 600, "cache_write_tokens": 300},
            "completion_tokens_details": {"reasoning_tokens": 250},
        },
    }
    assert normalize_usage(data) == {
        "inputTokens": 1000,
        "cachedInputTokens": 600,
        "cacheWriteTokens": 300,
        "outputTokens": 400,
        "reasoningTokens": 250,
        "finishReason": "length",
        "usageSource": "completion_tokens",
    }


def test_normalize_usage_corrects_gemini_thinking_tokens():
    # completion_tokens가 생각 토큰을 빼고 보고된 경우: 청구 출력은 total − prompt다(Q-0023).
    data = {
        "choices": [{"finish_reason": "stop"}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 530},
    }
    usage = normalize_usage(data)
    assert usage["outputTokens"] == 410 and usage["usageSource"] == "total_minus_prompt"
    assert usage["inputTokens"] == 120
    assert usage["cachedInputTokens"] is None and usage["reasoningTokens"] is None
    assert usage["cacheWriteTokens"] is None


def test_normalize_usage_cache_read_without_write_detail():
    data = {"usage": {"prompt_tokens": 900, "prompt_tokens_details": {"cached_tokens": 512}}}
    usage = normalize_usage(data)
    assert usage["cachedInputTokens"] == 512 and usage["cacheWriteTokens"] is None


def test_normalize_usage_without_total_uses_completion():
    usage = normalize_usage(
        {"choices": [{}], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}
    )
    assert usage["outputTokens"] == 3 and usage["usageSource"] == "completion_tokens"
    assert usage["finishReason"] is None


def test_normalize_usage_missing_is_none_not_zero():
    usage = normalize_usage({"choices": [{"finish_reason": "stop"}]})
    assert usage == {
        "inputTokens": None,
        "cachedInputTokens": None,
        "cacheWriteTokens": None,
        "outputTokens": None,
        "reasoningTokens": None,
        "finishReason": "stop",
        "usageSource": "missing",
    }


def test_chat_response_fills_usage_and_token_fields(capture):
    _, _, replies = capture
    replies.append(ok(usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 530}))
    response = OpenAICompatTextModel(GEMINI, "gemini-3.8-flash").complete(chat())
    assert response.usage["usageSource"] == "total_minus_prompt"
    assert response.input_tokens == 120 and response.output_tokens == 410
    assert response.finish_reason == "stop"


def test_400_is_not_retried_and_masks_key(capture, monkeypatch):
    sent, sleeps, replies = capture
    secret = "sk-test-secret-value-123"
    monkeypatch.setenv("CFP_DIALECT_KEY", secret)
    replies.append(
        httpx.Response(
            400,
            json={
                "error": {
                    "message": f"Unsupported parameter: 'temperature'. key {secret} rejected",
                    "type": "invalid_request_error",
                }
            },
        )
    )
    model = OpenAICompatTextModel(OPENAI, "gpt-6.1-sol", api_key_env="CFP_DIALECT_KEY")
    with pytest.raises(ProviderRequestError) as info:
        model.complete(chat())
    err = info.value
    assert len(sent) == 1 and sleeps == []
    assert err.status == 400
    assert "Unsupported parameter" in err.provider_message
    assert secret not in err.provider_message and secret not in str(err)
    assert "***" in err.provider_message and "400" in str(err)
    assert isinstance(err, RuntimeError) and isinstance(err, FactoryError)


def test_4xx_without_json_uses_body_prefix(capture):
    sent, _, replies = capture
    replies.append(httpx.Response(401, text="x" * 900))
    with pytest.raises(ProviderRequestError) as info:
        OpenAICompatTextModel(RELAY, "m").complete(chat())
    assert len(sent) == 1
    assert info.value.status == 401 and info.value.provider_message == "x" * 500


def test_vision_400_is_not_retried(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(PNG)
    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(400, json={"error": {"message": "bad image"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = OpenAICompatVisionModel(OPENAI, "judge", client=client, sleep=lambda s: None)
        with pytest.raises(ProviderRequestError, match="bad image"):
            model.judge(VisionRequest("s4", "cf-x/f1#qa", "판정", (("a", str(image)),)))
    assert len(calls) == 1


def test_429_is_retried_then_succeeds(capture):
    sent, sleeps, replies = capture
    replies.extend([httpx.Response(429, json={"error": {"message": "slow down"}}), ok()])
    response = OpenAICompatTextModel(OPENAI, "gpt-6.1-sol", max_retries=2).complete(chat())
    assert response.text == "{}"
    assert len(sent) == 2 and sleeps == [1.0]


def test_429_exhausted_keeps_runtime_error(capture):
    sent, sleeps, replies = capture
    replies.extend([httpx.Response(429), httpx.Response(503)])
    with pytest.raises(RuntimeError, match="공급자 호출 실패: status 503") as info:
        OpenAICompatTextModel(OPENAI, "gpt-6.1-sol", max_retries=1).complete(chat())
    assert not isinstance(info.value, ProviderRequestError)
    assert len(sent) == 2 and sleeps == [1.0]
