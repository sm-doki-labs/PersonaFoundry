"""실패 슬롯·첫 응답·독립 평가를 보존하는 합성 검사."""

from __future__ import annotations

import importlib
import importlib.util

import pytest


def protocol():
    assert importlib.util.find_spec("character_factory_poc.stages.persona_quality.protocol")
    return importlib.import_module("character_factory_poc.stages.persona_quality.protocol")


def test_scene_does_not_assume_rejected_agreement():
    p = protocol()
    turn = p.UserTurn(
        user="그럼 다른 얘기 하자.",
        branches=[{"contains": "좋아", "user": "합의한 시간이 언제였지?"}],
    )
    assert p.next_user(turn, "그날은 어려워.") == "그럼 다른 얘기 하자."
    assert p.next_user(turn, "좋아. 내일 다섯 시에 보자.") == "합의한 시간이 언제였지?"


def test_cohort_rejects_duplicate_slots_and_wrong_scene_size():
    p = protocol()
    with pytest.raises(ValueError):
        p.Scene(id="long", turns=[{"user": "안녕"}])
    with pytest.raises(ValueError):
        p.Slot(id="../outside", characterId="c", recipe="new", root=".", scenes=[])


def test_missing_human_review_cannot_qualify(tmp_path):
    assert importlib.util.find_spec("character_factory_poc.stages.persona_quality.report")
    report = importlib.import_module("character_factory_poc.stages.persona_quality.report")
    result = report.report_qualification(tmp_path)
    assert result["status"] == "NOT_RUN"


def test_missing_response_keeps_slot_in_denominator(tmp_path):
    from character_factory_poc.common.store import write_once_json
    from character_factory_poc.stages.persona_quality.report import report_qualification

    scenes = [
        dict(
            id=f"s{i}",
            turns=[dict(user="평범한 대화")] * 6,
            expectedChoices={1: "다른 선택"} if i < 5 else {},
        )
        for i in range(6)
    ]
    scenes.append(dict(id="long", turns=[dict(user="평범한 대화")] * 24))
    cohort = dict(
        id="dev",
        split="development",
        profile={},
        recipeHash="a" * 64,
        rubricHash="b" * 64,
        slots=[dict(id="one", characterId="c", recipe="new", root=str(tmp_path), scenes=scenes)],
    )
    write_once_json(tmp_path / "cohort.json", cohort)
    result = report_qualification(tmp_path)
    assert result["status"] == "NOT_QUALIFIED"
    assert result["plannedArtifacts"] == 1
    assert result["completedArtifacts"] == 0
    assert result["failedSlots"] == ["one"]


def test_preflight_rejects_missing_exact_tokenizer_before_calls(tmp_path):
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.persona_quality.protocol import Cohort
    from character_factory_poc.stages.persona_quality.run import run_qualification

    scenes = [
        dict(
            id=f"s{i}",
            turns=[dict(user="평범한 대화")] * 6,
            expectedChoices={1: "행동"} if i < 5 else {},
        )
        for i in range(6)
    ]
    scenes.append(dict(id="long", turns=[dict(user="일상")] * 24))
    cohort = Cohort.model_validate(
        dict(
            id="dev",
            split="development",
            profile={
                "modelBinding": {
                    "model": "fake-text",
                    "maxOutputTokens": 1000,
                    "provider": "fake",
                    "providerPath": "fake",
                    "reasoningSettings": {},
                }
            },
            recipeHash="a" * 64,
            rubricHash="b" * 64,
            slots=[
                dict(id="one", characterId="c", recipe="new", root=str(tmp_path), scenes=scenes)
            ],
        )
    )
    model = FakeTextModel()
    with pytest.raises(ValueError, match="exact model tokenizer"):
        run_qualification(
            Context.load(tmp_path, execute=True),
            cohort,
            tmp_path / "run",
            dialogue_model=model,
            token_counter=None,
        )
    assert not model.requests
    assert not (tmp_path / "run").exists()


def test_first_replies_accumulate_and_resume_without_redraw(tmp_path):
    from character_factory_poc.common.store import read_json, write_once_json
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.persona_quality.protocol import Cohort
    from character_factory_poc.stages.persona_quality.run import run_qualification
    from tests.test_formation_contracts import pair

    scenes = [
        dict(
            id=f"s{i}",
            turns=[dict(user="일상 대화")] * 6,
            expectedChoices={1: "기대 행동"} if i < 5 else {},
        )
        for i in range(6)
    ]
    scenes.append(dict(id="long", turns=[dict(user="이어서 말해줘")] * 24))
    cohort = Cohort.model_validate(
        dict(
            id="dev",
            split="development",
            profile={
                "modelBinding": {
                    "model": "fake-text",
                    "maxOutputTokens": 1000,
                    "provider": "fake",
                    "providerPath": "fake",
                    "reasoningSettings": {},
                }
            },
            recipeHash="a" * 64,
            rubricHash="b" * 64,
            slots=[
                dict(id="one", characterId="c", recipe="new", root=str(tmp_path), scenes=scenes)
            ],
        )
    )
    prompt = tmp_path / "pair.json"
    write_once_json(prompt, pair("prompt-pair-v1"))
    model = FakeTextModel()
    model.add("DIALOGUE", lambda r: "내 얘기도 해볼게.")
    ctx = Context.load(tmp_path, execute=True)
    run = tmp_path / "run"
    kwargs = dict(
        dialogue_model=model,
        token_counter=lambda ms: len(ms) * 10,
        formation_runner=lambda *_: prompt,
    )
    run_qualification(ctx, cohort, run, **kwargs)
    assert len(model.requests) == 60
    assert len(model.requests[1].messages) == 4
    assert len(model.requests[-1].messages) == 48
    assert not (run / "failures/one.json").exists()
    first = (run / "dialogues/one/long/24.json").read_bytes()
    run_qualification(ctx, cohort, run, **kwargs)
    assert len(model.requests) == 60
    assert (run / "dialogues/one/long/24.json").read_bytes() == first
    from character_factory_poc.stages.persona_quality.report import report_qualification

    result = report_qualification(run)
    assert result["status"] == "METRICS_ONLY" and result["completedArtifacts"] == 1
    path = run / "dialogues/one/long/24.json"
    data = read_json(path)
    data["assistant"] = "사후 수정된 답"
    import json

    path.write_text(json.dumps(data))
    assert report_qualification(run)["status"] == "NOT_QUALIFIED"


def test_interrupted_judge_never_redraws_on_resume(tmp_path):
    from character_factory_poc.providers.base import ChatResponse
    from character_factory_poc.stages.persona_quality.judge import triage_scene

    class Judge:
        model = "anthropic/claude"
        name = "stub"
        calls = 0

        def complete(self, req):
            self.calls += 1
            if self.calls == 1:
                return ChatResponse("invalid", 1, 1, 1, self.model, self.name)
            raise RuntimeError("unknown transport outcome")

    model = Judge()
    dest = tmp_path / "triage.json"
    with pytest.raises(RuntimeError):
        triage_scene(model, "google/gemini", [{"turn": 1, "assistant": "원문"}], dest)
    assert model.calls == 2
    triage_scene(model, "google/gemini", [{"turn": 1, "assistant": "원문"}], dest)
    assert model.calls == 2


def dev_cohort(tmp_path):
    from character_factory_poc.stages.persona_quality.protocol import Cohort

    scenes = [
        dict(
            id=f"s{i}",
            turns=[dict(user="평범한 대화")] * 6,
            expectedChoices={1: "행동"} if i < 5 else {},
        )
        for i in range(6)
    ]
    scenes.append(dict(id="long", turns=[dict(user="일상")] * 24))
    return Cohort.model_validate(
        dict(
            id="dev",
            split="development",
            profile={
                "modelBinding": {
                    "model": "fake-text",
                    "maxOutputTokens": 1000,
                    "provider": "fake",
                    "providerPath": "fake",
                    "reasoningSettings": {},
                }
            },
            recipeHash="a" * 64,
            rubricHash="b" * 64,
            slots=[
                dict(id="one", characterId="c", recipe="new", root=str(tmp_path), scenes=scenes)
            ],
        )
    )


def test_provider_binding_checked_before_formation(tmp_path):
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.persona_quality.run import run_qualification

    cohort = dev_cohort(tmp_path)
    cohort.profile["modelBinding"]["providerPath"] = "a-different-provider"
    model = FakeTextModel()
    with pytest.raises(ValueError, match="provider/settings"):
        run_qualification(
            Context.load(tmp_path, execute=True),
            cohort,
            tmp_path / "run",
            dialogue_model=model,
            token_counter=lambda _: 1,
        )
    assert not model.requests
    assert not (tmp_path / "run").exists()


def test_full_formation_budget_reserved_before_callback(tmp_path):
    from dataclasses import replace

    from character_factory_poc.common.config import BudgetConfig
    from character_factory_poc.common.errors import BudgetExceeded
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.persona_quality.run import run_qualification

    ctx = Context.load(tmp_path, execute=True)
    ctx.config = replace(ctx.config, budget=BudgetConfig(max_calls_per_command=60))
    called = []
    with pytest.raises(BudgetExceeded):
        run_qualification(
            ctx,
            dev_cohort(tmp_path),
            tmp_path / "run",
            dialogue_model=FakeTextModel(),
            token_counter=lambda _: 1,
            formation_runner=lambda *_: called.append("called"),
        )
    assert not called
