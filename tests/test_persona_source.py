"""승인 정본 전달 회귀 검사. 모든 캐릭터·대화는 합성 자료다."""

from __future__ import annotations

import json

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.s3_plan.variants import run_s3_variants
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.synthetic import prompter_output
from tests.support.web_gates import trait_sheet_for
from tests.test_persona_pipeline import _fake_models, _import
from tests.test_persona_pipeline import ctx as ctx
from tests.test_plan_variants import ready as ready


def test_v2_preserves_canon_and_source_hash_in_both_prompts(ready):
    context, agents, cid = ready
    folder = run_s3_variants(context, cid)
    approve_gate(
        context, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"}
    )
    plan = json.loads((folder / "plan.json").read_text())
    agents.set("s7", lambda req: trait_sheet_for(context, cid))
    agents.set("s8", lambda req: prompter_output())
    run_s7(context, cid)
    out = run_s8(context, cid, [])
    pair = json.loads((out / "prompt-pair.json").read_text())
    for mode in ("long", "short"):
        text = pair[mode]["text"]
        assert str(plan["age"]) + "세" in text
        assert plan["job"] in text
        assert plan["background"] in text
        assert all(v in text for v in plan["voiceExamples"])
        assert all(c["arc"] in text for c in plan["chapterArc"])
    source = json.loads((out / "source-plan.json").read_text())
    assert source["sourceSha256"] == sha256_file(folder / "plan.json")
    assert "appearanceRev" not in source["plan"]
    assert "evidence" not in source["plan"]
    sent = json.loads((out / "workspace/inputs/character-plan.json").read_text())
    assert sent == source


def test_legacy_plan_preserves_identity_and_chapter_without_invented_facts(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    text, judge = _fake_models(cid)
    ctx.use_models(text, judge)
    run_s7(ctx, cid)
    out = run_s8(ctx, cid, [])
    pair = json.loads((out / "prompt-pair.json").read_text())
    assert "24세" in pair["short"]["text"]
    assert "비 오는 책방 창가" in pair["short"]["text"]
    source = json.loads((out / "source-plan.json").read_text())
    assert "gender" not in source["plan"] and "background" not in source["plan"]


def test_oversized_canon_fails_before_any_s8_model_call(ready):
    context, agents, cid = ready
    # A valid large source must never be silently cut to fit the short prompt.
    original = agents.by_stage["s3-variants"]

    def huge(req):
        data = original(req)
        for p in data["variants"]:
            p["background"] = "합성 배경 문장이 길게 이어진다. " * 250
        return data

    agents.set("s3-variants", huge)
    run_s3_variants(context, cid)
    approve_gate(
        context, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"}
    )
    agents.set("s7", lambda req: trait_sheet_for(context, cid))
    agents.set("s8", lambda req: prompter_output())
    run_s7(context, cid)
    before = len(context._text.requests)
    with pytest.raises(ValueError, match="정본.*상한"):
        run_s8(context, cid, [])
    assert len(context._text.requests) == before


def test_legacy_voice_keeps_all_dialogue_habits(ctx, tmp_path):
    cid = _import(ctx, tmp_path)
    text, judge = _fake_models(cid)
    ctx.use_models(text, judge)
    sheet_path = run_s7(ctx, cid)
    habits = json.loads(sheet_path.read_text())["card"]["dialogueHabits"]
    out = run_s8(ctx, cid, [])
    pair = json.loads((out / "prompt-pair.json").read_text())
    for mode in ("long", "short"):
        assert all(value in pair[mode]["text"] for value in habits.values())


def test_unusable_generated_budget_fails_before_paid_request(ctx, tmp_path):
    from dataclasses import replace

    from character_factory_poc.common.schema import validate
    from character_factory_poc.stages.s8_prompts.build import (
        assemble,
        load_sections,
        load_system_rules,
    )
    from character_factory_poc.stages.s8_prompts.source import canonical_sections, project_plan

    cid = _import(ctx, tmp_path)
    text, judge = _fake_models(cid)
    ctx.use_models(text, judge)
    sheet_path = run_s7(ctx, cid)
    plan_path = ctx.character_dir(cid) / "s3-plan/pr1/plan.json"
    plan = validate("character-plan-v1", json.loads(plan_path.read_text()))
    sheet = validate("trait-sheet-v1", json.loads(sheet_path.read_text()))
    sections = load_sections()["sections"]
    rules, _ = load_system_rules(ctx)
    canonical = canonical_sections(project_plan(plan, sha256_file(plan_path)), sheet)
    base = len(assemble(sections, dict.fromkeys(sections, ""), plan.name, rules, canonical))
    ctx.config = replace(ctx.config, stages={"s8": {"short_prompt_max_chars": base + 3}})
    before = len(text.requests)
    with pytest.raises(ValueError, match="생성.*예산"):
        run_s8(ctx, cid, [])
    assert len(text.requests) == before


def test_resume_keeps_frozen_pair_when_current_rules_no_longer_fit(ctx, tmp_path):
    from dataclasses import replace

    cid = _import(ctx, tmp_path)
    text, judge = _fake_models(cid)
    ctx.use_models(text, judge)
    run_s7(ctx, cid)
    out = run_s8(ctx, cid, [])
    frozen_pair = (out / "prompt-pair.json").read_bytes()
    # Synthetic crash checkpoint: pair is saved; probe has not been written yet.
    (out / "prompt-probe.json").unlink()
    ctx.state(cid).transition("s8", "REJECTED")
    ctx.state(cid).transition("s8", "RUNNING")
    ctx.config = replace(ctx.config, stages={"s8": {"short_prompt_max_chars": 1}})
    before = len(text.requests)
    assert run_s8(ctx, cid, []) == out
    assert (out / "prompt-pair.json").read_bytes() == frozen_pair
    assert len(text.requests) == before
