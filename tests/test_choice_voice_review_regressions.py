import json

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.persona_quality.choice_voice_protocol import validate_development
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s7_traits.voice import bind_voice, load_voice_pack
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.test_choice_voice_development import development_case
from tests.test_choice_voice_flow import choice_voice_case
from tests.test_voice_assets import voice_asset


def test_review_r1_audit_must_cover_the_actual_voice_source(tmp_path):
    _, cohort = development_case(tmp_path)
    rows = []
    for i, row in enumerate(cohort.splitManifest.rows):
        other = tmp_path / f"unrelated-{i}.json"
        write_once_json(other, {"different": i})
        rows.append(
            row.model_copy(
                update={"path": str(other), "sha256": sha256_file(other), "fieldPath": ""}
            )
        )
    manifest = cohort.splitManifest.model_copy(update={"rows": rows})
    with pytest.raises(ValueError, match="source|audit"):
        validate_development(cohort.model_copy(update={"splitManifest": manifest}))


def test_review_r2_current_policy_change_blocks_pending_g6(tmp_path):
    ctx, _, cid = choice_voice_case(tmp_path)
    run_s7(ctx, cid)
    run_s8(ctx, cid, [])
    policy = ctx.config.stages["s7"]["voice_policy"]
    raw = read_json(policy)
    raw["assignments"][cid] = "missing-pack"
    from pathlib import Path

    Path(policy).write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="voice|VOICE"):
        approve_gate(ctx, cid, "G6", dict(decision="APPROVE", reviewer="tester"))
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"


def test_review_r3_d_prompt_cannot_be_declared_a_generated_control(tmp_path):
    _, cohort = development_case(tmp_path)
    from character_factory_poc.stages.persona_quality.choice_voice_protocol import FileAsset

    validate_development(cohort)
    d = next(s for s in cohort.slots if s.arm == "D")
    c = next(s for s in cohort.slots if s.arm == "C")
    # Refresh both public hashes too: actual producer replay must still reject D
    # being substituted for C, even if the receipt is relabelled consistently.
    receipt = read_json(c.producer.verify())
    receipt["pairSha256"] = d.pair.sha256
    changed = tmp_path / "relabelled-producer.json"
    write_once_json(changed, receipt)
    producer = FileAsset(path=str(changed), sha256=sha256_file(changed))
    slots = [
        s.model_copy(update={"pair": d.pair, "producer": producer}) if s.arm == "C" else s
        for s in cohort.slots
    ]
    with pytest.raises(ValueError, match="producer|prompt|control"):
        validate_development(cohort.model_copy(update={"slots": slots}))


def test_review_r4_negative_target_is_not_a_positive_keyword_match(tmp_path):
    path, index = voice_asset(tmp_path)
    pack = load_voice_pack(path, approval_index=index)
    binding = bind_voice(
        dict(characterId="x", voiceSummary="반말을 절대 쓰지 않고 모든 상대에게 존댓말만 사용한다"),
        [pack],
        dict(assignments={}, rules=[dict(requires=["반말"], packId="soft")]),
    )
    assert binding.status == "VOICE_SOURCE_MISSING"


def test_review_r5_completed_formal_collection_resumes_at_its_call_cap(tmp_path):
    from character_factory_poc.common.schema import dump
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.persona_quality.protocol import Cohort, Scene, Slot
    from character_factory_poc.stages.persona_quality.run import run_qualification

    ctx, development = development_case(tmp_path)
    d = next(s for s in development.slots if s.arm == "D")
    scenes = [
        Scene(
            id=f"eval{i}",
            turns=[
                dict(user="그 얘기 조금 더 해줘", branches=[]) for _ in range(6 if i < 6 else 24)
            ],
            expectedChoices={1: "조건에 맞는 선택"} if i < 5 else {},
        )
        for i in range(7)
    ]
    rows = [dump(row) for row in development.splitManifest.rows]
    for i, scene in enumerate(scenes):
        path = tmp_path / f"scene-{i}.json"
        write_once_json(path, json.loads(scene.model_dump_json()))
        rows.append(
            dict(
                id=f"eval-{i}",
                path=str(path),
                sha256=sha256_file(path),
                sourceGroupId=f"eval-g{i}",
                originalConversationId=f"eval-c{i}",
                parentSourceIds=[],
                derivedFrom=[],
                sceneFamilyId=scene.id,
                split="development",
            )
        )
    manifest = tmp_path / "split.json"
    write_once_json(manifest, dict(auditStatus="PASS", rows=rows))
    profile = dict(development.profile)
    profile["splitManifestSha256"] = sha256_file(manifest)
    cohort = Cohort(
        id="formal-resume",
        split="development",
        profile=profile,
        recipeHash="1" * 64,
        rubricHash="2" * 64,
        overlapAudit=str(manifest),
        formation=False,
        slots=[
            Slot(
                id="one",
                characterId=d.characterId,
                recipe="new",
                root=str(ctx.config.root),
                scenes=scenes,
            )
        ],
    )
    ctx.max_calls = 60
    model = FakeTextModel("fake-dialogue", {"*": "응, 알겠어"})
    out = tmp_path / "formal-evaluation"
    run_qualification(ctx, cohort, out, dialogue_model=model, token_counter=lambda _: 10)
    assert len(model.requests) == 60
    run_qualification(ctx, cohort, out, dialogue_model=model, token_counter=lambda _: 10)
    assert len(model.requests) == 60


def test_review_r6_comparison_system_rules_must_be_identical(tmp_path):
    from pathlib import Path

    from character_factory_poc.stages.persona_quality.producers import prepare_development_pair

    _, cohort = development_case(tmp_path)
    c = next(s for s in cohort.slots if s.arm == "C")
    assets = {
        name: Path(ref["path"]) for name, ref in read_json(c.producer.verify())["assets"].items()
    }
    changed = tmp_path / "changed-rules.md"
    changed.write_text(assets["systemRules"].read_text() + "모든 답변 끝에 반드시 하트를 붙인다.")
    assets["systemRules"] = changed
    pair, producer = prepare_development_pair("C", assets, tmp_path / "changed-producer")
    slots = [
        s.model_copy(update={"pair": pair, "producer": producer}) if s.arm == "C" else s
        for s in cohort.slots
    ]
    with pytest.raises(ValueError, match="system|compiler|controlled"):
        validate_development(cohort.model_copy(update={"slots": slots}))


@pytest.mark.parametrize("target", [{}, {"positiveTags": ["반말"]}, {"requiredTags": [""]}])
def test_review_r7_empty_structured_target_does_not_override_negation(tmp_path, target):
    path, index = voice_asset(tmp_path)
    pack = load_voice_pack(path, approval_index=index)
    binding = bind_voice(
        dict(characterId="x", voiceSummary="반말을 절대 쓰지 않고 존댓말만 사용한다"),
        [pack],
        dict(assignments={"x": "soft"}, targets={"x": target}),
    )
    assert binding.status == "VOICE_SOURCE_MISSING"
