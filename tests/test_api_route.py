"""공식 API 호출 경로(`api`) 해석·선택·화면·HTTP 경계 테스트(명세 §24.2, LLD §22.2).

가짜 응답과 monkeypatch만 쓰며 네트워크·유료 호출을 하지 않는다. 키 값은 테스트용 문자열이다.
"""

import json
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from character_factory_poc.common import text_deck
from character_factory_poc.common.api_routes import (
    FAMILY_DEFAULTS,
    billing_for,
    family_of,
    official_model_id,
    validate_env_name,
)
from character_factory_poc.common.config import ProviderConfig, load_config
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.web.settings import load_settings
from character_factory_poc.web.text_pipeline import install_text_pipeline_routes

OPENAI = ("https://api.openai.com/v1", "OPENAI_API_KEY")
GEMINI = ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY")
# task → (계열, basic_test 공식 모델, demo 공식 모델, reasoning_effort)
EXPECTED = {
    "brief": ("openai", "gpt-6.1-sol", "gpt-6.1-sol", "high"),
    "personality": ("gemini", "gemini-3.8-flash", "gemini-3.8-flash", "high"),
    "consistency": ("openai", "gpt-6.1-sol", "gpt-6.1-sol", "high"),
    "voice": ("gemini", "gemini-3.8-flash", "gemini-4-argon", "high"),
    "scenarios": ("openai", "gpt-6.1-sol", "gpt-6.1-sol", "medium"),
    "sft_answers": ("gemini", "gemini-3.8-flash", "gemini-4-argon", "high"),
    "screening": ("openai", "gpt-6.1-terra", "gpt-6.1-terra", "high"),
    "adjudication": ("openai", "gpt-6.1-sol", "gpt-6.1-sol", "high"),
    "repair": ("gemini", "gemini-3.8-flash", "gemini-4-argon", "high"),
}
OPENAI_SECRET = "sk-test-openai-secret-value"
GEMINI_SECRET = "gm-test-gemini-secret-value"


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def configured(tmp_path, *, profile="basic_test", route="api", extra=""):
    (tmp_path / "factory.toml").write_text(
        f'[text_pipeline]\nenabled=true\nprofile="{profile}"\nroute="{route}"\n' + extra,
        encoding="utf-8",
    )
    return load_config(tmp_path)


def test_family_rules_match_contract():
    assert FAMILY_DEFAULTS == {
        "openai": {"base_url": OPENAI[0], "api_key_env": OPENAI[1]},
        "gemini": {"base_url": GEMINI[0], "api_key_env": GEMINI[1]},
    }
    assert family_of("gpt-6.1-sol") == "openai"
    assert family_of("gemini-4-argon") == "gemini"
    assert family_of("google-antigravity/gemini-3.8-flash") == "gemini"
    assert family_of("claude-x") is None
    assert family_of("google-antigravity/claude-x") is None
    assert official_model_id("google-antigravity/gemini-4-argon") == "gemini-4-argon"
    assert official_model_id("gpt-6.1-terra") == "gpt-6.1-terra"


@pytest.mark.parametrize("profile", ["basic_test", "demo"])
def test_every_deck_task_resolves_to_official_api(tmp_path, profile):
    cfg = configured(tmp_path, profile=profile)
    assert [s["id"] for s in text_deck.deck()["stages"]] == list(EXPECTED)
    for task, (family, flash_model, demo_model, effort) in EXPECTED.items():
        binding = cfg.text_binding(task)
        base_url, env = OPENAI if family == "openai" else GEMINI
        model = flash_model if profile == "basic_test" else demo_model
        assert binding["route"] == "api"
        assert binding["profile"] == profile
        assert binding["family"] == family
        assert binding["model"] == model
        assert binding["reasoning_effort"] == effort
        assert binding["provider"] == {
            "adapter": "openai_compat",
            "base_url": base_url,
            "model": model,
            "api_key_env": env,
            "extra": {
                "reasoning_effort": effort,
                "timeout_s": 240.0,
                "max_retries": 0,
                "stream": False,
            },
        }
        assert billing_for(cfg.task_provider(task), "api") == {
            "route": "api",
            "family": family,
            "class": "api_billed",
        }


def test_opencodex_binding_shape_is_unchanged(tmp_path):
    # 형성 fingerprint가 해시하는 반환값이므로 api 경로가 생겨도 키와 값이 그대로여야 한다.
    binding = configured(tmp_path, route="opencodex").text_binding("voice")
    assert set(binding) == {
        "task",
        "profile",
        "route",
        "baselineModel",
        "model",
        "reasoning_effort",
        "provider",
        "deckSha256",
    }
    assert binding["provider"] == {
        "adapter": "openai_compat",
        "base_url": "http://127.0.0.1:10100/v1",
        "model": "google-antigravity/gemini-3.8-flash",
        "api_key_env": "",
        "extra": {"reasoning_effort": "high", "timeout_s": 240.0, "max_retries": 0},
    }


def test_family_overrides_and_model_mapping_take_priority(tmp_path):
    cfg = configured(
        tmp_path,
        extra="""
[text_pipeline.routes.api.families.gemini]
base_url="https://gemini-proxy.example/v1"
api_key_env="CFP_GEMINI_KEY"
timeout_s=30
[text_pipeline.routes.api.models]
"google-antigravity/gemini-3.8-flash"="gemini-3.8-flash-preview"
"gpt-6.1-terra"="gpt-6.1-terra-2026-11"
""",
    )
    voice = cfg.text_binding("voice")["provider"]
    assert voice["base_url"] == "https://gemini-proxy.example/v1"
    assert voice["api_key_env"] == "CFP_GEMINI_KEY"
    assert voice["model"] == "gemini-3.8-flash-preview"
    assert voice["extra"]["timeout_s"] == 30.0
    screening = cfg.text_binding("screening")
    assert screening["model"] == "gpt-6.1-terra-2026-11"
    assert screening["provider"]["base_url"] == OPENAI[0]
    assert screening["provider"]["extra"]["timeout_s"] == 240.0
    assert cfg.text_binding("brief")["model"] == "gpt-6.1-sol"
    # 덮어쓴 주소가 공식 호스트가 아니면 과금 구분도 공식 청구로 적지 않는다.
    assert billing_for(cfg.task_provider("voice"), "api")["class"] == "unverified"


def test_route_level_timeout_is_default_and_family_overrides_it(tmp_path):
    cfg = configured(
        tmp_path,
        extra="""
[text_pipeline.routes.api]
timeout_s=90
[text_pipeline.routes.api.families.gemini]
timeout_s=30
""",
    )
    assert cfg.text_binding("brief")["provider"]["extra"]["timeout_s"] == 90.0
    assert cfg.text_binding("voice")["provider"]["extra"]["timeout_s"] == 30.0


def test_model_without_known_family_is_rejected(tmp_path, monkeypatch):
    cfg = configured(tmp_path)
    source = text_deck.deck()
    source["stages"][0] = dict(source["stages"][0], model="claude-x")
    monkeypatch.setattr(text_deck, "deck", lambda: source)
    with pytest.raises(ValueError, match="계열"):
        cfg.text_binding("brief")
    assert cfg.text_binding("voice")["family"] == "gemini"


@pytest.mark.parametrize(
    "extra",
    [
        '[text_pipeline.routes.api.families.anthropic]\nbase_url="https://x.example/v1"\n',
        '[text_pipeline.routes.api.families.openai]\nbase_url="https://u:p@api.openai.com/v1"\n',
        '[text_pipeline.routes.api.families.openai]\nbase_url="https://api.openai.com/v1?k=1"\n',
        '[text_pipeline.routes.api.families.openai]\nbase_url="ftp://api.openai.com/v1"\n',
        '[text_pipeline.routes.api.families.openai]\napi_key_env="sk-inline-value"\n',
        '[text_pipeline.routes.api.families.openai]\napi_key_env=""\n',
        '[text_pipeline.routes.api.families.openai]\napi_key="sk-inline-value"\n',
        '[text_pipeline.routes.api]\nbase_url="https://api.openai.com/v1"\n',
        '[text_pipeline.routes.api]\nadapter="fake"\n',
        '[text_pipeline.routes.api.models]\n"gpt-6.1-sol"=""\n',
    ],
)
def test_bad_api_settings_are_rejected_without_echoing_values(tmp_path, extra):
    cfg = configured(tmp_path, extra=extra)
    with pytest.raises(ValueError) as caught:
        cfg.text_binding("brief")
    assert "sk-inline-value" not in str(caught.value)


def test_billing_classes():
    assert billing_for(ProviderConfig()) == {"route": "fake", "family": None, "class": "none"}
    openai = ProviderConfig("openai_compat", OPENAI[0], "gpt-6.1-sol", OPENAI[1])
    assert billing_for(openai) == {"route": "direct", "family": "openai", "class": "api_billed"}
    gemini = ProviderConfig("openai_compat", GEMINI[0], "gemini-4-argon", GEMINI[1])
    assert billing_for(gemini, "api")["class"] == "api_billed"
    relay = ProviderConfig(
        "openai_compat", "http://127.0.0.1:10100/v1", "google-antigravity/gemini-4-argon"
    )
    assert billing_for(relay, "opencodex") == {
        "route": "opencodex",
        "family": "gemini",
        "class": "relay_equivalent",
    }
    local = replace(relay, base_url="http://localhost:8080/v1")
    assert billing_for(local)["class"] == "relay_equivalent"
    other = ProviderConfig("openai_compat", "https://test.invalid/v1", "server-model")
    assert billing_for(other, "test") == {"route": "test", "family": None, "class": "unverified"}
    assert billing_for(other)["class"] == "unverified"


def test_billing_route_rules_override_host_only_where_spec_says():
    official = ProviderConfig("openai_compat", OPENAI[0], "gpt-6.1-sol", OPENAI[1])
    local = ProviderConfig("openai_compat", "http://127.0.0.1:10100/v1", "gpt-6.1-sol")
    remote = ProviderConfig("openai_compat", "https://relay.example/v1", "gpt-6.1-sol")
    # test 경로는 공식 호스트를 가리켜도 미확인이다.
    assert billing_for(official, "test")["class"] == "unverified"
    assert billing_for(local, "test")["class"] == "unverified"
    # opencodex 경로는 주소가 바뀌어도 중계 환산이다.
    assert billing_for(remote, "opencodex")["class"] == "relay_equivalent"
    assert billing_for(official, "opencodex")["class"] == "relay_equivalent"
    # api 경로는 호스트 규칙을 따른다.
    assert billing_for(official, "api")["class"] == "api_billed"
    assert billing_for(local, "api")["class"] == "relay_equivalent"
    assert billing_for(remote, "api")["class"] == "unverified"
    assert billing_for(ProviderConfig(), "test")["class"] == "none"


@pytest.mark.parametrize("name", ["OPENAI_API_KEY", "_CFP_KEY", "CFP_2", "A" * 64])
def test_env_name_check_accepts_upper_snake_names(name):
    assert validate_env_name(name) is None


@pytest.mark.parametrize(
    "name",
    [
        "",
        "cfp_key",
        "Cfp_Key",
        "1CFP",
        "CFP-KEY",
        "CFP KEY",
        "CFP_KEY\n",
        "A" * 65,
        "sk-proj-inlinesecretvalue",
        "AIzaSyInlineSecretValue",
        None,
        7,
    ],
)
def test_env_name_check_rejects_values_without_echoing(name):
    with pytest.raises(ValueError) as caught:
        validate_env_name(name)
    if isinstance(name, str) and name:
        assert name not in str(caught.value)


@pytest.mark.parametrize(
    ("route", "extra"),
    [
        ("opencodex", '[text_pipeline.routes.opencodex]\napi_key_env="sk-inlinesecret"\n'),
        ("opencodex", '[text_pipeline.routes.opencodex]\napi_key_env="cfp_relay_key"\n'),
        (
            "test",
            '[text_pipeline.routes.test]\nbase_url="https://test.invalid/v1"\n'
            'api_key_env="AIzaSyInlineSecret"\n',
        ),
        (
            "test",
            '[text_pipeline.routes.test]\nbase_url="https://test.invalid/v1"\n'
            f'api_key_env="{"K" * 65}"\n',
        ),
        ("api", '[text_pipeline.routes.api.families.gemini]\napi_key_env="gemini_key"\n'),
    ],
)
def test_every_route_applies_env_name_check(tmp_path, route, extra):
    cfg = configured(tmp_path, route=route, extra=extra)
    with pytest.raises(ValueError, match="환경변수 이름") as caught:
        cfg.text_binding("voice")
    assert "Inline" not in str(caught.value) and "inline" not in str(caught.value)


def test_test_route_binding_is_unchanged_by_env_name_check(tmp_path):
    cfg = configured(
        tmp_path,
        route="test",
        extra='[text_pipeline.routes.test]\nbase_url="https://test.invalid/v1"\n'
        'api_key_env="CFP_TEST_KEY"\n',
    )
    binding = cfg.text_binding("voice")
    assert "family" not in binding
    assert binding["provider"] == {
        "adapter": "openai_compat",
        "base_url": "https://test.invalid/v1",
        "model": "google-antigravity/gemini-3.8-flash",
        "api_key_env": "CFP_TEST_KEY",
        "extra": {"reasoning_effort": "high", "timeout_s": 240.0, "max_retries": 0},
    }
    assert billing_for(cfg.task_provider("voice"), "test")["class"] == "unverified"


def test_select_api_route_persists_without_keys(tmp_path):
    cfg = configured(tmp_path, route="opencodex")
    chosen = text_deck.select(cfg, route="api")
    assert chosen == {"profile": "basic_test", "route": "api"}
    path = tmp_path / "work/text-pipeline-selection.json"
    assert json.loads(path.read_text("utf-8")) == chosen
    reloaded = load_config(tmp_path)
    assert reloaded.text_binding("voice")["route"] == "api"
    assert text_deck.select(reloaded, profile="demo") == {"profile": "demo", "route": "api"}
    assert load_config(tmp_path).text_binding("voice")["model"] == "gemini-4-argon"


def test_bad_api_route_selection_keeps_previous_selection(tmp_path):
    cfg = configured(
        tmp_path,
        route="opencodex",
        extra='[text_pipeline.routes.api.families.gemini]\nbase_url="https://u:p@x.example/v1"\n',
    )
    with pytest.raises(ValueError):
        text_deck.select(cfg, route="api")
    assert not (tmp_path / "work/text-pipeline-selection.json").exists()


def test_web_lists_api_route_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_SECRET)
    root = tmp_path / "factory"
    root.mkdir()
    configured(root, route="opencodex")

    class NoJobs:
        def active_jobs(self):
            return []

    app = FastAPI()
    install_text_pipeline_routes(app, root, load_settings(root), NoJobs())
    with TestClient(app) as client:
        body = client.get("/api/text-pipeline").json()
        routes = {r["id"]: r for r in body["routes"]}
        assert routes["api"] == {"id": "api", "label": "공식 API", "available": True, "reason": ""}
        switched = client.post("/api/text-pipeline/selection", json={"route": "api"})
        assert switched.status_code == 200
        body = switched.json()
    assert body["route"] == "api"
    tasks = {t["id"]: t for t in body["tasks"]}
    assert tasks["voice"]["model"] == "gemini-3.8-flash"
    assert tasks["scenarios"]["model"] == "gpt-6.1-sol"
    dumped = json.dumps(body)
    for leaked in (
        OPENAI_SECRET,
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "api.openai.com",
        "generativelanguage",
    ):
        assert leaked not in dumped


def test_web_marks_unresolvable_api_route_unavailable(tmp_path):
    root = tmp_path / "factory"
    root.mkdir()
    configured(
        root,
        route="opencodex",
        extra='[text_pipeline.routes.api.families.openai]\nbase_url="https://api.openai.com/v1?x=1"\n',
    )

    class NoJobs:
        def active_jobs(self):
            return []

    app = FastAPI()
    install_text_pipeline_routes(app, root, load_settings(root), NoJobs())
    with TestClient(app) as client:
        routes = {r["id"]: r for r in client.get("/api/text-pipeline").json()["routes"]}
        assert routes["api"]["available"] is False
        assert "?x=1" not in routes["api"]["reason"]
        assert client.post("/api/text-pipeline/selection", json={"route": "api"}).status_code == 400


def test_api_route_reaches_official_hosts_with_family_keys(tmp_path, monkeypatch):
    cfg = configured(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", GEMINI_SECRET)
    sent = []

    def post(client, url, **kw):
        sent.append((url, kw))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "model": kw["json"]["model"],
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    req = ChatRequest("AGENT", "s7", (Message("user", "json"),), "cf-x/tr1")
    ctx = Context(cfg, execute=True)
    ctx.task_model("cf-x", ctx.budget(), "scenarios").complete(req)
    ctx.task_model("cf-x", ctx.budget(), "voice").complete(replace(req, ref="cf-x/tr2"))
    assert len(sent) == 2
    (openai_url, openai_kw), (gemini_url, gemini_kw) = sent
    assert openai_url == "https://api.openai.com/v1/chat/completions"
    assert openai_kw["json"]["model"] == "gpt-6.1-sol"
    assert openai_kw["json"]["reasoning_effort"] == "medium"
    assert openai_kw["headers"]["Authorization"] == f"Bearer {OPENAI_SECRET}"
    assert gemini_url == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert gemini_kw["json"]["model"] == "gemini-3.8-flash"
    assert gemini_kw["json"]["reasoning_effort"] == "high"
    assert gemini_kw["headers"]["Authorization"] == f"Bearer {GEMINI_SECRET}"
    rows = ctx.ledger("cf-x").calls()
    assert [r["textBinding"]["route"] for r in rows] == ["api", "api"]
    assert [r["textBinding"]["family"] for r in rows] == ["openai", "gemini"]
    dumped = json.dumps(rows)
    assert OPENAI_SECRET not in dumped and GEMINI_SECRET not in dumped


def test_missing_family_key_is_rejected_before_http(tmp_path, monkeypatch):
    cfg = configured(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_SECRET)
    seen = []
    monkeypatch.setattr(httpx.Client, "post", lambda client, url, **kw: seen.append(url))
    ctx = Context(cfg, execute=True)
    with pytest.raises(ValueError, match="gemini 계열") as caught:
        ctx.task_model("cf-x", ctx.budget(), "voice")
    assert "GEMINI_API_KEY" not in str(caught.value)
    assert seen == []
