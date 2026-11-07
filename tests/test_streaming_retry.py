"""D-0084: 공식 API 스트리밍(Gemini 생각 요약 포함)과 전송 실패의 예산 안 재시도."""

import json

import httpx
import pytest

from character_factory_poc.common.budget import RunBudget
from character_factory_poc.common.errors import ProviderRequestError, ProviderTransportError
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.providers.base import ChatRequest, ChatResponse, Message
from character_factory_poc.providers.openai_compat import OpenAICompatTextModel
from character_factory_poc.providers.tracked import TrackedTextModel

GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"
OPENAI = "https://api.openai.com/v1"
REQ = ChatRequest("AGENT", "s3-variants", (Message("user", "json 하나"),), "cf-x/pr1#1", 32000)


class FakeStream:
    def __init__(self, status=200, lines=(), body=b""):
        self.status_code, self._lines, self._body = status, list(lines), body
        self.is_success = 200 <= status < 300

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_lines(self):
        yield from self._lines

    def read(self):
        return self._body

    def json(self):
        return json.loads(self._body)

    @property
    def text(self):
        return self._body.decode()


def data(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False)


def patch_stream(monkeypatch, *responses):
    sent = []
    queue = list(responses)

    def stream(client, method, url, **kw):
        sent.append((url, kw))
        return queue.pop(0)

    monkeypatch.setattr(httpx.Client, "stream", stream)
    return sent


def test_gemini_stream_body_moves_effort_to_thinking_config_with_thoughts():
    body = OpenAICompatTextModel(
        GEMINI, "gemini-3.8-flash", reasoning_effort="high", stream=True
    ).body(REQ)
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert "reasoning_effort" not in body
    assert body["extra_body"]["google"]["thinking_config"] == {
        "thinking_level": "high",
        "include_thoughts": True,
    }
    assert body["max_tokens"] == 32000


def test_openai_stream_keeps_effort_and_relay_never_streams():
    body = OpenAICompatTextModel(OPENAI, "gpt-6.1-sol", reasoning_effort="high", stream=True).body(
        REQ
    )
    assert body["stream"] is True and body["reasoning_effort"] == "high"
    assert "extra_body" not in body
    relay = OpenAICompatTextModel("http://127.0.0.1:10100/v1", "x", stream=True)
    assert not relay.streaming() and "stream" not in relay.body(REQ)


def test_stream_joins_content_strips_thoughts_and_reads_last_usage(monkeypatch):
    lines = [
        data({"choices": [{"delta": {"role": "assistant", "content": "<thought>생각 요약"}}]}),
        data(
            {"choices": [{"delta": {"content": " 계속</thought>"}}], "usage": {"prompt_tokens": 10}}
        ),
        ": keep-alive",
        data(
            {
                "choices": [{"delta": {"content": '{"a": 1}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 40},
            }
        ),
        "data: [DONE]",
    ]
    sent = patch_stream(monkeypatch, FakeStream(lines=lines))
    model = OpenAICompatTextModel(
        GEMINI, "gemini-3.8-flash", reasoning_effort="high", stream=True, max_retries=0
    )
    resp = model.complete(REQ)
    assert resp.text == '{"a": 1}' and resp.finish_reason == "stop"
    assert resp.usage["outputTokens"] == 30 and resp.usage["usageSource"] == "total_minus_prompt"
    assert len(sent) == 1


def test_stream_cut_off_or_broken_is_transport_error(monkeypatch):
    patch_stream(monkeypatch, FakeStream(lines=[data({"choices": [{"delta": {"content": "{"}}]})]))
    model = OpenAICompatTextModel(
        OPENAI, "gpt-6.1-sol", reasoning_effort="high", stream=True, max_retries=0
    )
    with pytest.raises(ProviderTransportError) as caught:
        model.complete(REQ)
    assert caught.value.kind == "disconnect" and isinstance(caught.value, RuntimeError)
    patch_stream(monkeypatch, FakeStream(lines=["data: {broken"]))
    with pytest.raises(ProviderTransportError) as caught:
        model.complete(REQ)
    assert caught.value.kind == "malformed_stream"


def test_stream_rejection_is_request_error_without_retry(monkeypatch):
    body = json.dumps({"error": {"message": "bad argument"}}).encode()
    sent = patch_stream(monkeypatch, FakeStream(400, body=body), FakeStream(400, body=body))
    model = OpenAICompatTextModel(GEMINI, "gemini-3.8-flash", stream=True, max_retries=2)
    with pytest.raises(ProviderRequestError, match="bad argument"):
        model.complete(REQ)
    assert len(sent) == 1


class Flaky:
    name = "openai_compat"
    model = "gpt-6.1-sol"
    max_retries = 0

    def __init__(self, failures):
        self.failures, self.calls = failures, []

    def complete(self, request):
        self.calls.append(request.ref)
        if len(self.calls) <= self.failures:
            raise ProviderTransportError("disconnect", "peer closed connection")
        return ChatResponse(
            "{}",
            10,
            5,
            1,
            self.model,
            self.name,
            "stop",
            usage={
                "inputTokens": 10,
                "cachedInputTokens": None,
                "cacheWriteTokens": None,
                "outputTokens": 5,
                "reasoningTokens": None,
                "finishReason": "stop",
                "usageSource": "completion_tokens",
            },
        )


def budget(tmp_path):
    return RunBudget(
        tmp_path / "b.json",
        max_calls=5,
        max_tokens=10**6,
        max_cost_usd=5.0,
        input_rate_per_million=2.5,
        output_rate_per_million=10.0,
    )


def test_transport_failure_is_retried_once_with_its_own_reservation_and_row(tmp_path):
    inner, ledger, run = Flaky(1), Ledger(tmp_path / "ledger"), budget(tmp_path)
    billing = {"route": "api", "family": "openai", "class": "api_billed"}
    model = TrackedTextModel(
        inner, ledger, run, billing=billing, transport_retries=1, sleep=lambda s: None
    )
    model.complete(REQ)
    assert inner.calls == ["cf-x/pr1#1", "cf-x/pr1#1~transport1"]
    rows = ledger.calls()
    assert [r["ok"] for r in rows] == [False, True]
    assert rows[0]["usageSource"] == "transport_failed:disconnect" and rows[0]["estCostUsd"] is None
    states = sorted(
        r["status"] for r in json.loads((tmp_path / "b.json").read_text())["reservations"].values()
    )
    # 끊긴 시도는 청구됐을 수 있어 예약(상한 금액)을 그대로 남긴다.
    assert states == ["RESERVED", "SETTLED"]


def test_transport_retry_is_bounded(tmp_path):
    inner = Flaky(2)
    model = TrackedTextModel(
        inner, Ledger(tmp_path / "l"), budget(tmp_path), transport_retries=1, sleep=lambda s: None
    )
    with pytest.raises(ProviderTransportError):
        model.complete(REQ)
    assert len(inner.calls) == 2
    none = TrackedTextModel(
        Flaky(1), Ledger(tmp_path / "m"), budget(tmp_path / "x"), transport_retries=0
    )
    with pytest.raises(ProviderTransportError):
        none.complete(REQ)


def test_api_route_stream_flag_reaches_the_adapter(tmp_path):
    from character_factory_poc.common.config import load_config
    from character_factory_poc.providers.factory import make_text_model

    (tmp_path / "factory.toml").write_text(
        '[text_pipeline]\nenabled=true\nprofile="basic_test"\nroute="api"\n'
        "[text_pipeline.routes.api]\nstream=true\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert make_text_model(cfg.task_provider("voice")).streaming()
    assert make_text_model(cfg.task_provider("brief")).streaming()
