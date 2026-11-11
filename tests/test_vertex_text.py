"""D-0149: Vertex AI OpenAI 호환 경로와 접근 토큰 자동 갱신."""

import httpx
import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.providers import openai_compat as oc
from character_factory_poc.providers import vertex_auth
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.providers.factory import make_text_model
from character_factory_poc.providers.vertex_auth import GcloudToken, vertex_openai_base_url


@pytest.fixture(autouse=True)
def no_real_gcloud(monkeypatch):
    """시험에서 실제 gcloud를 부르지 않는다(실제 토큰이 출력에 섞이지 않게)."""

    def refuse(cmd):
        raise AssertionError("시험에서 실제 gcloud를 불렀다")

    monkeypatch.setattr(vertex_auth, "_run", refuse)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_token_is_cached_and_refreshed_after_ttl():
    calls, clock = [], Clock()

    def runner(cmd):
        calls.append(cmd)
        return f"tok{len(calls)}\n"

    tok = GcloudToken(ttl_s=100, runner=runner, clock=clock)
    assert tok.get() == "tok1" and tok.get() == "tok1"
    clock.t = 99
    assert tok.get() == "tok1"
    clock.t = 100
    assert tok.get() == "tok2"
    assert tok.refresh() == "tok3" and len(calls) == 3


def test_token_failure_does_not_leak_output():
    def runner(cmd):
        raise FileNotFoundError("gcloud")

    with pytest.raises(RuntimeError, match="application-default login"):
        GcloudToken(runner=runner).get()
    with pytest.raises(RuntimeError, match="비었다"):
        GcloudToken(runner=lambda cmd: "  ").get()


def test_base_url_by_location():
    assert vertex_openai_base_url("p1") == (
        "https://aiplatform.googleapis.com/v1/projects/p1/locations/global/endpoints/openapi"
    )
    assert vertex_openai_base_url("p1", "us-central1").startswith(
        "https://us-central1-aiplatform.googleapis.com/"
    )
    with pytest.raises(ValueError, match="project"):
        vertex_openai_base_url("")


def _ok(model="google/gemini-3.8-flash"):
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"content": "네, 반갑습니다."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        },
    )


def test_vertex_adapter_sends_bearer_token_and_retries_once_on_401(monkeypatch):
    seen = []
    replies = [httpx.Response(401, json={"error": {"message": "expired"}}), _ok()]

    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json, headers):
            seen.append((url, headers["Authorization"], json["model"]))
            return replies.pop(0)

    monkeypatch.setattr(oc.httpx, "Client", Client)
    tokens = iter(["old", "new"])
    monkeypatch.setattr(vertex_auth, "_run", lambda cmd: next(tokens))
    cfg = ProviderConfig(
        adapter="vertex_openai",
        model="google/gemini-3.8-flash",
        extra={"project": "p1", "reasoning_effort": "low"},
    )
    model = make_text_model(cfg)
    resp = model.complete(
        ChatRequest("PROBE", "demo", (Message("user", "안녕"),), "r1", temperature=0.8)
    )
    assert resp.text == "네, 반갑습니다."
    auth = [s[1] for s in seen]
    assert auth == ["Bearer old", "Bearer new"], "토큰 순서가 다르다"
    assert seen[0][0].endswith("/locations/global/endpoints/openapi/chat/completions")


def test_vertex_adapter_needs_model_and_project():
    with pytest.raises(ValueError, match="model"):
        make_text_model(ProviderConfig(adapter="vertex_openai", extra={"project": "p"}))
    with pytest.raises(ValueError, match="project"):
        make_text_model(ProviderConfig(adapter="vertex_openai", model="google/x"))
