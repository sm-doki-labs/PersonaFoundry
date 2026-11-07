"""Deck selection must reach the real HTTP boundary without calling a network."""

import json
from dataclasses import replace

import httpx
import pytest

from character_factory_poc.cli import main
from character_factory_poc.common.config import load_config
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message


def configured(tmp_path, extra=""):
    (tmp_path / "factory.toml").write_text(
        '[agent]\nbackend="codex_exec"\nmodel="old-agent"\n'
        '[text_pipeline]\nenabled=true\nprofile="basic_test"\nroute="opencodex"\n' + extra,
        encoding="utf-8",
    )
    return load_config(tmp_path)


def test_default_flash_and_explicit_demo_reach_http_and_ledger(tmp_path, monkeypatch):
    cfg = configured(tmp_path)
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
    ctx.task_model("cf-x", ctx.budget(), "voice").complete(req)
    assert sent[-1][0] == "http://127.0.0.1:10100/v1/chat/completions"
    assert sent[-1][1]["json"]["model"] == "google-antigravity/gemini-3.8-flash"
    assert sent[-1][1]["json"]["reasoning_effort"] == "high"
    assert ctx.agent_backend("cf-x", ctx.budget(), "s7") is None
    row = ctx.ledger("cf-x").calls()[0]
    assert row["textBinding"]["profile"] == "basic_test"
    assert row["textBinding"]["task"] == "voice"
    assert main(["--root", str(tmp_path), "models", "select", "--profile", "demo"]) == 0
    ctx = Context.load(tmp_path, execute=True)
    ctx.task_model("cf-x", ctx.budget(), "voice").complete(replace(req, ref="cf-x/tr2"))
    assert sent[-1][1]["json"]["model"] == "google-antigravity/gemini-4-argon"
    ctx.task_model("cf-x", ctx.budget(), "personality").complete(req)
    assert sent[-1][1]["json"]["model"] == "google-antigravity/gemini-3.8-flash"
    ctx.task_model("cf-x", ctx.budget(), "scenarios").complete(req)
    assert sent[-1][1]["json"]["model"] == "gpt-6.1-sol"
    assert sent[-1][1]["json"]["reasoning_effort"] == "medium"


def test_unconfigured_test_route_does_not_change_current_selection(tmp_path, capsys):
    configured(tmp_path)
    assert main(["--root", str(tmp_path), "models", "select", "--route", "test"]) == 1
    assert not (tmp_path / "work/text-pipeline-selection.json").exists()
    assert "test" in capsys.readouterr().err
    assert load_config(tmp_path).text_binding("voice")["route"] == "opencodex"


def test_test_route_maps_models_and_uses_named_auth_env(tmp_path, monkeypatch):
    cfg = configured(
        tmp_path,
        """
[text_pipeline.routes.test]
adapter="openai_compat"
base_url="https://test.invalid/v1"
api_key_env="CFP_TEST_KEY"
[text_pipeline.routes.test.models]
"google-antigravity/gemini-3.8-flash"="flash-native"
""",
    )
    assert main(["--root", str(tmp_path), "models", "select", "--route", "test"]) == 0
    cfg = load_config(tmp_path)
    assert cfg.task_provider("voice").model == "flash-native"
    monkeypatch.setenv("CFP_TEST_KEY", "test-secret-value")
    seen = []

    def post(client, url, **kw):
        seen.append((url, kw))
        raise httpx.ConnectError("offline fixture")

    monkeypatch.setattr(httpx.Client, "post", post)
    monkeypatch.setattr("character_factory_poc.providers.tracked.time.sleep", lambda s: None)
    ctx = Context(cfg, execute=True)
    with pytest.raises(RuntimeError, match="공급자 호출 실패"):
        ctx.task_model("cf-x", ctx.budget(), "voice").complete(
            ChatRequest("AGENT", "s7", (Message("user", "json"),), "cf-x/tr1")
        )
    # D-0084: 전송 실패만 같은 모델·경로로 한 번 다시 보내고, 시도마다 원장 행을 남긴다.
    assert len(seen) == 2
    assert {url for url, _ in seen} == {"https://test.invalid/v1/chat/completions"}
    assert {kw["json"]["model"] for _, kw in seen} == {"flash-native"}
    assert seen[0][1]["headers"]["Authorization"] == "Bearer test-secret-value"
    rows = ctx.ledger("cf-x").calls()
    assert [r["ref"] for r in rows] == ["cf-x/tr1", "cf-x/tr1~transport1"]
    for row in rows:
        assert row["ok"] is False and row["model"] == "flash-native"
        assert row["textBinding"]["route"] == "test"
        assert row["usageSource"] == "transport_failed:disconnect"
        assert "test-secret-value" not in json.dumps(row)
    assert "test-secret-value" not in (tmp_path / "work/text-pipeline-selection.json").read_text()


def test_disabled_deck_keeps_legacy_fake_and_codex(tmp_path):
    ctx = Context.load(tmp_path, execute=True)
    assert not ctx.text_deck_enabled
    assert ctx.task_model("cf-x", ctx.budget(), "voice").name == "fake"


@pytest.mark.parametrize(
    "option",
    [
        'profile="typo"',
        'route="missing"',
    ],
)
def test_bad_selection_is_rejected_before_provider_calls(tmp_path, option):
    (tmp_path / "factory.toml").write_text("[text_pipeline]\nenabled=true\n" + option)
    with pytest.raises(ValueError):
        load_config(tmp_path).text_binding("voice")


def test_switching_route_invalidates_typed_step_resume(tmp_path, monkeypatch):
    from character_factory_poc.contracts.choice_design import SeedRequirementsDraft
    from character_factory_poc.pipeline.formation_step import run_typed_step

    configured(
        tmp_path,
        """
[text_pipeline.routes.test]
base_url="https://test.invalid/v1"
""",
    )
    seen = []

    def post(client, url, **kw):
        seen.append(url)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "requirements": [
                                        {
                                            "requirementId": "r1",
                                            "field": "personality",
                                            "quote": "조용함",
                                            "kind": "fixed",
                                        }
                                    ]
                                }
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    kw = dict(
        cid="cf-x",
        folder=tmp_path / "typed",
        role="seed_requirements",
        contract=SeedRequirementsDraft,
        stage="cv-requirements",
        inputs={"seed": "조용함"},
    )
    ctx = Context.load(tmp_path, execute=True)
    run_typed_step(ctx=ctx, **kw)
    run_typed_step(ctx=ctx, **kw)
    assert len(seen) == 1
    binding = json.loads((tmp_path / "typed/model-binding.json").read_text())
    assert binding["model"] == "gpt-6.1-sol"
    assert binding["textBinding"]["task"] == "brief"
    assert main(["--root", str(tmp_path), "models", "select", "--route", "test"]) == 0
    with pytest.raises(ValueError, match="fingerprint"):
        run_typed_step(ctx=Context.load(tmp_path, execute=True), **kw)
    assert len(seen) == 1


def test_deck_s8_compiles_approved_traits_without_any_model(tmp_path, monkeypatch):
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.s3_plan.common import new_character
    from character_factory_poc.stages.s7_traits.sheet import run_s7
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from tests.support.flow import approve_plan_v2, v2_plan
    from tests.support.synthetic import trait_sheet

    legacy = Context.load(tmp_path, execute=True)
    cid = new_character(legacy, "deck")
    plan = v2_plan(cid)
    approve_plan_v2(legacy, cid, plan)
    fake = FakeTextModel()
    fake.add("AGENT", lambda r: trait_sheet(cid, "pr1"))
    legacy.use_models(fake)
    run_s7(legacy, cid)
    cfg = configured(tmp_path)

    def no_http(*args, **kw):
        raise AssertionError("S8 must preserve approved material without LLM calls")

    monkeypatch.setattr(httpx.Client, "post", no_http)
    result = run_s8(Context(cfg, execute=True), cid, [])
    pair = json.loads((result / "prompt-pair.json").read_text())
    for text in (pair["long"]["text"], pair["short"]["text"]):
        assert plan["name"] in text
        assert all(trait in text for trait in plan["coreTraits"])
        assert all(item in text for item in plan["lifeAndTastes"])
        assert "PERSONA / LIFE_AND_TASTES" in text
        assert "CHAPTERS" not in text and "CHARACTER_EXAMPLES" not in text
    assert (result / "text-deck-binding.json").exists()


def test_s3_deck_uses_sol_constraints_flash_draft_and_argon_voice(tmp_path, monkeypatch):
    from character_factory_poc.stages.s3_plan.seed import write_seed
    from character_factory_poc.stages.s3_plan.variants import run_s3_variants
    from tests.support.flow import make_ctx, through_s2
    from tests.test_plan_variants import SEED, output

    legacy, _ = make_ctx(tmp_path)
    cid = through_s2(legacy)
    write_seed(legacy, cid, SEED)
    configured(tmp_path)
    assert main(["--root", str(tmp_path), "models", "select", "--profile", "demo"]) == 0
    models = []

    def post(client, url, **kw):
        model = kw["json"]["model"]
        models.append(model)
        if len(models) == 1:
            body = {
                "requirements": [
                    dict(
                        requirementId="r1",
                        field="personality",
                        quote=SEED["personality"],
                        kind="fixed",
                    )
                ]
            }
        else:
            body = output(cid)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "model": model,
                "choices": [{"message": {"content": json.dumps(body)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    folder = run_s3_variants(Context.load(tmp_path, execute=True), cid)
    assert (folder / "variants.json").exists()
    assert models == [
        "gpt-6.1-sol",
        "google-antigravity/gemini-3.8-flash",
        "google-antigravity/gemini-4-argon",
    ]


def test_deck_generation_cannot_execute_from_a_dry_run_context(tmp_path, monkeypatch):
    cfg = configured(tmp_path)

    def no_http(*args, **kwargs):
        raise AssertionError("dry-run must not reach HTTP")

    monkeypatch.setattr(httpx.Client, "post", no_http)
    ctx = Context(cfg, execute=False)
    with pytest.raises(ValueError, match="execute"):
        ctx.task_model("cf-x", ctx.budget(), "voice").complete(
            ChatRequest("AGENT", "s7", (Message("user", "json"),), "cf-x/tr1")
        )
