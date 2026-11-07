import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.persona_quality.choice_voice_protocol import DevelopmentCohortV2
from character_factory_poc.stages.persona_quality.report import report_qualification
from character_factory_poc.stages.persona_quality.run import plan_qualification, run_qualification
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.test_choice_voice_flow import choice_voice_case


def development_case(tmp_path):
    ctx, _, cid = choice_voice_case(tmp_path)
    trait = run_s7(ctx, cid)
    run_s8(ctx, cid, [])
    root = ctx.character_dir(cid)
    selection = read_json(root / "s3-plan/pr1/selection.json")

    def ref(path):
        return dict(path=str(path), sha256=sha256_file(path))

    binding = read_json(trait.parent / "voice-binding.json")
    draft = binding | dict(
        status="DRAFT",
        packId=None,
        packPath=None,
        packSha256=None,
        approvalIndexPath=None,
        approvalIndexSha256=None,
        examples=[],
        rules=["짧은 문장"],
        reason="generated control",
    )
    draft_path = tmp_path / "draft-voice.json"
    write_once_json(draft_path, draft)
    pack = read_json(binding["packPath"])
    rows = []
    for i, e in enumerate(pack["examples"]):
        source = tmp_path / "voice" / e["sourceFile"]
        rows.append(
            dict(
                id=f"voice-{i}",
                path=str(source),
                sha256=sha256_file(source),
                sourceGroupId=e["sourceGroupId"],
                originalConversationId=f"voice-conv-{i}",
                parentSourceIds=[],
                derivedFrom=[],
                sceneFamilyId=f"voice-scene-{i}",
                split="injection",
                fieldPath=e["fieldPath"],
            )
        )
    val = tmp_path / "voice/validation-source.json"
    rows.append(
        dict(
            id="validation",
            path=str(val),
            sha256=sha256_file(val),
            sourceGroupId="g-other",
            originalConversationId="validation-conv",
            parentSourceIds=[],
            derivedFrom=[],
            sceneFamilyId="validation-scene",
            split="voice-validation",
            fieldPath="line",
        )
    )
    scenes = [
        dict(
            id=f"scene{i}",
            turns=[dict(user=f"중립적인 합성 질문 {j}", branches=[]) for j in range(6)],
            expectedChoices={1: "조건에 맞게 선택한다"},
        )
        for i in range(2)
    ]
    # Actual frozen producer sources: A legacy direct, B new choices/direct,
    # C beats + generated voice, D identical beats + approved voice.
    from pathlib import Path

    from character_factory_poc.contracts.formation import (
        FormationDialogues,
        PersonaBlueprint,
        TraitSheet,
        load_quality_profile,
    )
    from character_factory_poc.stages.persona_quality.producers import prepare_development_pair
    from character_factory_poc.stages.s8_prompts.compiler import compile_persona
    from tests.test_formation_contracts import dialogues

    plan_path = root / "s3-plan/pr1/plan.json"
    bp_path = trait.parent / "blueprint.json"
    bp = read_json(bp_path)
    original_bp = dict(bp, schemaVersion="persona-blueprint-v1")
    original_bp.pop("approvedChoiceRef")
    original_bp["decisionRules"] = [
        {
            k: v
            for k, v in rule.items()
            if k not in {"choiceRuleId", "attention", "acceptedCost", "alternative"}
        }
        for rule in bp["decisionRules"]
    ]
    legacy_bp = tmp_path / "legacy-blueprint.json"
    write_once_json(legacy_bp, original_bp)
    profile_path = (
        Path(__file__).resolve().parents[1]
        / "src/character_factory_poc/resources/persona-quality-profile-v1.json"
    )
    rules_path = tmp_path / "development-system-rules.md"
    from character_factory_poc.stages.s8_prompts.build import load_system_rules

    rules_text, _ = load_system_rules(ctx)
    rules_path.write_text(rules_text)
    direct = dialogues()
    direct.update(
        characterId=cid,
        traitRevision=trait.parent.name,
        planSha256=sha256_file(plan_path),
        traitSheetSha256=sha256_file(trait),
        blueprintSha256=sha256_file(bp_path),
        sourceRefs=bp["sourceRefs"]
        + [
            dict(
                kind="blueprint",
                ref=str(bp_path),
                version=trait.parent.name,
                sha256=sha256_file(bp_path),
                fieldPath="decisionRules[0].firstMove",
                quote=bp["decisionRules"][0]["firstMove"],
            )
        ],
    )
    direct_path = tmp_path / "direct-dialogues.json"
    write_once_json(direct_path, direct)
    legacy_direct = dict(
        direct,
        blueprintSha256=sha256_file(legacy_bp),
        sourceRefs=[
            dict(r, sha256=sha256_file(legacy_bp), ref=str(legacy_bp))
            if r["kind"] == "blueprint"
            else r
            for r in direct["sourceRefs"]
        ],
    )
    legacy_direct_path = tmp_path / "legacy-dialogues.json"
    write_once_json(legacy_direct_path, legacy_direct)
    from character_factory_poc.common.schema import validate

    plan = validate(read_json(plan_path)["schemaVersion"], read_json(plan_path))
    legacy_bundle = compile_persona(
        plan,
        TraitSheet.model_validate(read_json(trait)),
        PersonaBlueprint.model_validate(original_bp),
        FormationDialogues.model_validate(legacy_direct),
        load_quality_profile(profile_path),
        source_hashes=dict(
            plan=sha256_file(plan_path),
            trait=sha256_file(trait),
            blueprint=sha256_file(legacy_bp),
            dialogues=sha256_file(legacy_direct_path),
        ),
        trait_revision=trait.parent.name,
        persona_version="legacy",
        rules_text=rules_text,
        rules_ref="development-frozen-v1",
    )
    legacy_bundle_path = tmp_path / "legacy-bundle.json"
    write_once_json(legacy_bundle_path, dump(legacy_bundle))
    generated_render = read_json(trait.parent / "rendered-dialogues.json")
    generated_render["voiceBindingSha256"] = sha256_file(draft_path)
    for scene in generated_render["dialogues"]:
        for turn in scene["turns"]:
            if turn["role"] == "assistant":
                turn["content"] = "그 조건부터 확인할래"
    generated_render_path = tmp_path / "generated-rendered.json"
    write_once_json(generated_render_path, generated_render)
    slots = []
    for arm in "ABCD":
        assets = dict(
            seed=root / selection["seed"]["path"],
            plan=plan_path,
            trait=trait,
            blueprint=legacy_bp if arm == "A" else bp_path,
            systemRules=rules_path,
        )
        if arm == "A":
            assets.update(
                profile=profile_path, dialogues=legacy_direct_path, legacyBundle=legacy_bundle_path
            )
        else:
            assets.update(
                choice=root / selection["choice"]["path"],
                compilerProfile=profile_path,
                voiceBinding=trait.parent / "voice-binding.json" if arm == "D" else draft_path,
                dialogues=direct_path
                if arm == "B"
                else generated_render_path
                if arm == "C"
                else trait.parent / "rendered-dialogues.json",
            )
        if arm in "CD":
            assets["beats"] = trait.parent / "formation-beats.json"
        if arm == "D":
            assets["voicePolicy"] = trait.parent / "voice-policy.json"
        pair, producer = prepare_development_pair(arm, assets, tmp_path / f"producer-{arm}")
        slots.append(
            dict(
                id=f"slot-{arm}",
                characterId=cid,
                arm=arm,
                pair=dump(pair),
                producer=dump(producer),
                scenes=scenes,
                **{
                    name: ref(assets[name]) if name in assets else None
                    for name in (
                        "seed",
                        "plan",
                        "blueprint",
                        "choice",
                        "beats",
                        "voiceBinding",
                        "voicePolicy",
                    )
                },
            )
        )
    profile = read_json(trait.parent / "profile.json")
    profile["modelBinding"] = dict(
        model="fake-dialogue",
        provider="fake",
        providerPath="fake",
        reasoningSettings={},
        maxOutputTokens=2400,
        contextLimit=24000,
        temperature=0.7,
    )
    return ctx, DevelopmentCohortV2(
        id="synthetic-development",
        profile=profile,
        recipeHash="1" * 64,
        splitManifest=dict(auditStatus="PASS", rows=rows),
        slots=slots,
    )


def test_development_collects_first_replies_and_never_qualifies(tmp_path):
    ctx, cohort = development_case(tmp_path)
    model = FakeTextModel("fake-dialogue", {"*": "응, 그 조건은 알겠어"})
    assert plan_qualification(cohort)["dialogueCalls"] == 48
    run = run_qualification(
        ctx, cohort, tmp_path / "evaluation", dialogue_model=model, token_counter=lambda _: 10
    )
    result = report_qualification(run)
    assert result["status"] == "METRICS_ONLY" and not result["qualityQualified"]
    assert result["completedReplies"] == 48 and result["completedArtifacts"] == 4
    run_qualification(ctx, cohort, run, dialogue_model=model, token_counter=lambda _: 10)
    assert len(model.requests) == 48


def test_review_packet_has_canon_blueprint_and_blind_voice_reference(tmp_path):
    ctx, cohort = development_case(tmp_path)
    model = FakeTextModel("fake-dialogue", {"*": "응, 알겠어"})
    run = run_qualification(
        ctx, cohort, tmp_path / "evaluation", dialogue_model=model, token_counter=lambda _: 10
    )
    packet = read_json(run / "review-packet.json")
    assert all(p["canonicalPlan"] and p["decisionRules"] and p["voiceReference"] for p in packet)
    assert (run / "human-reviews-template.json").is_file()


def test_missing_counter_stops_before_any_reply(tmp_path):
    ctx, cohort = development_case(tmp_path)
    model = FakeTextModel("fake-dialogue", {"*": "응"})
    with pytest.raises(ValueError, match="tokenizer"):
        run_qualification(
            ctx, cohort, tmp_path / "evaluation", dialogue_model=model, token_counter=None
        )
    assert not model.requests
