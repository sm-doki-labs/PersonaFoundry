"""Anthropic Messages adapter and the S3 planner route. No network."""

import json

import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.anthropic_messages import (
    AnthropicTextModel,
    collect_stream,
    normalize_usage,
)
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.providers.factory import make_text_model


def _request(user="짧은 질문", **kw):
    return ChatRequest(
        kind="AGENT",
        stage="s3",
        ref="synthetic/pr1/x",
        messages=(Message("system", "지시"), Message("user", user)),
        max_output_tokens=kw.pop("max_output_tokens", 500),
        temperature=0.0,
        response_json=True,
        **kw,
    )


def _sse(*events):
    return [f"data: {json.dumps(e, ensure_ascii=False)}" for e in events]


def test_body_omits_temperature_and_caches_long_source():
    model = AnthropicTextModel("claude-opus-5-5", effort="high", max_output_tokens=1000)
    body = model.body(_request("원문" * 3000, max_output_tokens=50_000))
    assert "temperature" not in body and body["system"].startswith("지시")
    assert body["output_config"] == {"effort": "high"} and body["max_tokens"] == 1000
    block = body["messages"][0]["content"][0]
    assert block["cache_control"] == {"type": "ephemeral"} and "JSON" in body["system"]
    assert block["text"] == "원문" * 3000  # The cached source block stays byte-identical.
    assert "cache_control" not in model.body(_request())["messages"][0]["content"][0]


def test_stream_keeps_answer_text_only_and_counts_cached_input():
    lines = _sse(
        {
            "type": "message_start",
            "message": {
                "model": "claude-opus-5-5",
                "usage": {
                    "input_tokens": 10,
                    "cache_read_input_tokens": 90,
                    "cache_creation_input_tokens": 0,
                },
            },
        },
        {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "숨김"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": '{"a":'}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "1}"}},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 7},
        },
        {"type": "message_stop"},
    )
    data = collect_stream(lines)
    usage = normalize_usage(data["usage"], data["stop_reason"])
    assert data["text"] == '{"a":1}'
    assert (usage["inputTokens"], usage["cachedInputTokens"], usage["outputTokens"]) == (100, 90, 7)
    assert usage["finishReason"] == "stop"
    with pytest.raises(ValueError):
        collect_stream(lines[:-1])
    with pytest.raises(ValueError):
        collect_stream(_sse({"type": "error", "error": {"type": "overloaded_error"}}))


def test_factory_and_planner_route(tmp_path):
    built = make_text_model(
        ProviderConfig(adapter="anthropic", model="claude-opus-5-5", extra={"effort": "high"})
    )
    assert isinstance(built, AnthropicTextModel) and built.effort == "high"
    (tmp_path / "factory.toml").write_text(
        '[providers.text]\nadapter="fake"\n[providers.planner]\nadapter="fake"\nmodel="planner-x"\n'
    )
    ctx = Context.load(tmp_path, execute=True)
    assert ctx.planner_model("c", ctx.budget()).inner.model == "planner-x"
    (tmp_path / "factory.toml").write_text('[providers.text]\nadapter="fake"\nmodel="text-x"\n')
    ctx = Context.load(tmp_path, execute=True)
    assert ctx.planner_model("c", ctx.budget()).inner.model == "text-x"
