"""공식 이미지 연결 계약. 합성 PNG와 가짜 HTTP만 사용한다."""

import base64
import json

import cv2
import httpx
import numpy as np
import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import ImageGenerationError
from character_factory_poc.providers.base import ImageRequest
from character_factory_poc.providers.factory import make_image_model, make_vision_model


@pytest.fixture
def png():
    return cv2.imencode(".png", np.full((32, 32, 3), 120, dtype=np.uint8))[1].tobytes()


def adapter(**extra):
    return make_image_model(ProviderConfig(adapter="openai_images", extra=extra))


def transport(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original(**kw, transport=httpx.MockTransport(handler))
    )


def test_generation_uses_official_api_and_records_usage(monkeypatch, png):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "data": [{"b64_json": base64.b64encode(png).decode()}],
                "usage": {"input_tokens": 123, "output_tokens": 456},
            },
        )

    transport(monkeypatch, respond)
    result = adapter(quality="high", complexity="medium").generate(
        ImageRequest("s4", "portrait", "test", negative_prompt="extra people", size="720x1280")
    )
    assert len(calls) == 1
    req = calls[0]
    assert str(req.url) == "https://api.openai.com/v1/images/generations"
    assert req.headers["authorization"] == "Bearer synthetic-key"
    body = json.loads(req.content)
    assert body["model"] == "gpt-image-2.6-sunburst"
    assert body["size"] == "720x1280"
    assert body["n"] == 1 and body["output_format"] == "png"
    assert body["complexity"] == "medium" and body["quality"] == "high"
    assert "extra people" in body["prompt"]
    assert result.data == png and result.provider == "openai_images"
    assert result.input_tokens == 123 and result.output_tokens == 456
    assert result.est_cost_usd is None  # token mix absent: never pretend API is free


def test_references_use_edits_with_all_input_bytes(monkeypatch, tmp_path, png):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    refs = [tmp_path / "one.png", tmp_path / "two.png"]
    for ref in refs:
        ref.write_bytes(png)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]})

    transport(monkeypatch, respond)
    adapter().generate(
        ImageRequest("s4", "preserve face", "test", reference_images=tuple(map(str, refs)))
    )
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.openai.com/v1/images/edits"
    assert calls[0].content.count(b'name="image[]"') == 2
    assert calls[0].content.count(png) == 2
    assert b"input_fidelity" not in calls[0].content


def test_missing_key_and_missing_reference_fail_before_http(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    transport(monkeypatch, lambda _: pytest.fail("network must not be called"))
    with pytest.raises(ImageGenerationError, match="환경변수"):
        adapter().generate(ImageRequest("s4", "x", "test"))
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    with pytest.raises(ImageGenerationError, match="참조 이미지"):
        adapter().generate(
            ImageRequest("s4", "x", "test", reference_images=(str(tmp_path / "missing.png"),))
        )


def test_official_adapter_rejects_relay():
    with pytest.raises(ValueError, match="공식"):
        make_image_model(
            ProviderConfig(adapter="openai_images", base_url="http://127.0.0.1:10100/v1")
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": [{"b64_json": base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()}]},
        {"data": [{"b64_json": "!!!!"}]},
        {"data": [{"b64_json": base64.b64encode(b"not-png").decode()}]},
    ],
)
def test_bad_response_is_not_an_image(monkeypatch, payload):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    transport(monkeypatch, lambda _: httpx.Response(200, json=payload))
    with pytest.raises(ImageGenerationError):
        adapter().generate(ImageRequest("s4", "x", "test"))


def test_rejection_masks_secret_and_does_not_retry(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "invalid synthetic-secret"}})

    transport(monkeypatch, respond)
    with pytest.raises(ImageGenerationError) as exc:
        adapter().generate(ImageRequest("s4", "x", "test"))
    assert "synthetic-secret" not in str(exc.value)
    assert "401" in str(exc.value) and len(calls) == 1


def test_vision_factory_honors_direct_api_limits():
    model = make_vision_model(
        ProviderConfig(
            adapter="openai_compat",
            base_url="https://api.openai.com/v1",
            model="gpt-6.1-sol",
            api_key_env="OPENAI_API_KEY",
            extra={"timeout_s": 90, "max_retries": 0},
        )
    )
    assert model.timeout == 90 and model.max_retries == 0


def test_reference_and_precheck_plan_do_not_call_paid_image_free():
    from types import SimpleNamespace

    from character_factory_poc.stages.s0_source.precheck import _plan
    from character_factory_poc.stages.s4_frames.reference import plan_calls

    cfg = ProviderConfig(adapter="openai_images")
    ctx = SimpleNamespace(config=SimpleNamespace(provider=lambda _: cfg))
    assert plan_calls(ctx)[0].est_cost_usd is None
    step = _plan(ctx, ["image"], "720p")[0]
    assert step["model"] == "gpt-image-2.6-sunburst"
    assert step["estimatedUsd"] is None
