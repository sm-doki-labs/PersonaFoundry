"""Reproductions from independent review, using the actual stage runners."""

import json
from dataclasses import replace

import httpx
import pytest

from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import CheckFailed, NeedsInputError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.common import new_character
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.approve import approve_g6
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.flow import approve_plan_v2, v2_plan
from tests.support.synthetic import trait_sheet
from tests.test_text_model_deck import configured


@pytest.fixture
def ready(tmp_path, monkeypatch):
    # 이 시험들은 성격 시트 조립기를 본다. 장부 경로는 test_trait_ledger가 본다.
    configured(tmp_path, extra="[stages.s7]\ntrait_ledger = false\n")
    ctx = Context.load(tmp_path, execute=True)
    # D-0080: 최신 기획서(v2)로 고정한다. 구형 v1은 S8이 빈 섹션으로 거절한다.
    cid = new_character(ctx, "review")
    approve_plan_v2(ctx, cid, v2_plan(cid))
    sheet = trait_sheet(cid, "pr1")

    def post(client, url, **kw):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "model": "google-antigravity/gemini-3.8-flash",
                "choices": [{"message": {"content": json.dumps(sheet)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    run_s7(ctx, cid)

    def no_http(*args, **kwargs):
        raise AssertionError("S8 must not call a model")

    monkeypatch.setattr(httpx.Client, "post", no_http)
    return ctx, cid, sheet


def test_compiler_keeps_the_exceptions_to_approved_choices(ready):
    ctx, cid, sheet = ready
    folder = run_s8(ctx, cid, [])
    text = (folder / "long.md").read_text()
    exceptions = sheet["choice"]["switchConditions"] + [
        p["switch"] for p in sheet["card"]["judgmentPriorities"]
    ]
    assert all(condition in text for condition in exceptions)
    assert "switchConditions" not in text and "activeWhen" not in text


def test_compiler_honors_existing_system_rules_setting(ready, tmp_path):
    ctx, cid, _ = ready
    custom = tmp_path / "custom-rules.md"
    custom.write_text("실제로 들은 정보와 상상한 정보를 구분한다.")
    stages = ctx.config.stages | {"s8": {"system_rules_path": str(custom)}}
    ctx = Context(replace(ctx.config, stages=stages), execute=True)
    folder = run_s8(ctx, cid, [])
    pair = json.loads((folder / "prompt-pair.json").read_text())
    assert pair["systemRulesRef"] == str(custom)
    assert custom.read_text() in pair["long"]["text"]


def test_g6_change_request_blocks_identical_recompilation_until_sources_change(ready):
    ctx, cid, _ = ready
    first = run_s8(ctx, cid, [])
    approve_g6(
        ctx,
        cid,
        {
            "decision": "REQUEST_CHANGES",
            "reviewer": "tester",
            "requestedChanges": [{"field": "voice", "note": "존댓말로 바꾼다"}],
        },
    )
    with pytest.raises(NeedsInputError, match="S7|S3"):
        run_s8(ctx, cid, [])
    assert not (first.parent / "pv2").exists()
    assert ctx.state(cid).gate("G6").status == "REJECTED"
    custom = ctx.config.root / "polite-rules.md"
    custom.write_text("상대에게 존댓말로 말한다.")
    stages = ctx.config.stages | {"s8": {"system_rules_path": str(custom)}}
    updated = Context(replace(ctx.config, stages=stages), execute=True)
    second = run_s8(updated, cid, [])
    assert second.name == "pv2" and custom.read_text() in (second / "long.md").read_text()


def test_profile_switch_never_relabels_flash_source_as_argon(ready):
    from character_factory_poc.common.text_deck import select

    ctx, cid, _ = ready
    select(ctx.config, profile="pre_demo_completion_check")
    folder = run_s8(Context(load_config(ctx.config.root), execute=True), cid, [])
    binding = json.loads((folder / "text-deck-binding.json").read_text())
    assert binding["sourceGeneration"]["responseModel"] == "google-antigravity/gemini-3.8-flash"
    assert binding["sourceGeneration"]["binding"]["profile"] == "basic_test"
    assert binding["selectedConfiguration"]["model"] == "google-antigravity/gemini-4-argon"
    assert binding["completionCheck"] == "NOT_RUN"


def test_s3_voice_finalizer_cannot_change_comparison_text(tmp_path, monkeypatch):
    from character_factory_poc.stages.s3_plan.seed import write_seed
    from character_factory_poc.stages.s3_plan.variants import run_s3_variants
    from tests.support.flow import make_ctx, through_s2
    from tests.test_plan_variants import SEED, output

    legacy, _ = make_ctx(tmp_path)
    cid = through_s2(legacy)
    write_seed(legacy, cid, SEED)
    configured(tmp_path)
    count = 0

    def post(client, url, **kw):
        nonlocal count
        count += 1
        if count == 1:
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
            if count >= 3:
                body["axisNote"] = "새 비교 설명으로 바꿨다"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "model": kw["json"]["model"],
                "choices": [{"message": {"content": json.dumps(body)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    ctx = Context.load(tmp_path, execute=True)
    with pytest.raises(CheckFailed, match="axisNote"):
        run_s3_variants(ctx, cid)
    assert ctx.state(cid).stage("s3").status == "CHECK_FAILED"
