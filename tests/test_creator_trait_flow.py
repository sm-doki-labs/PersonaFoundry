import pytest

from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s3_plan.seed import load_latest_seed, write_seed
from character_factory_poc.stages.s3_plan.trait_recommendations import resolve_traits
from character_factory_poc.stages.s3_plan.variants import run_s3_variants
from character_factory_poc.stages.s7_traits.formation import canonical_plan
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.test_choice_design_flow import setup_choices
from tests.test_choice_voice_flow import choice_voice_case


def selected_case(tmp_path):
    ctx, agents, cid = setup_choices(tmp_path)
    write_seed(ctx, cid, dump(load_latest_seed(ctx, cid)), trait_ids=["P01-T1"])
    return ctx, agents, cid


def test_creator_requirement_without_a_linked_behavior_rule_is_rejected(tmp_path):
    ctx, agents, cid = selected_case(tmp_path)
    original = agents.by_stage["cv-choices"]

    def omit(req):
        body = original(req)
        for design in body["designs"]:
            for rule in design["rules"]:
                rule["requirementIds"] = [
                    r for r in rule["requirementIds"] if not r.startswith("creator-")
                ]
        return body

    agents.set("cv-choices", omit)
    with pytest.raises(ValueError, match="creator.*rule"):
        run_s3_variants(ctx, cid)


def test_creator_metadata_alone_is_not_accepted_as_implementation_evidence(tmp_path):
    ctx, agents, cid = selected_case(tmp_path)
    original = agents.by_stage["cv-choice-review"]
    behavior = resolve_traits(["P01-T1"])[0].behavior

    def metadata_only(req):
        body = original(req)
        for item in body["items"]:
            if item["requirementId"].startswith("creator-"):
                item["quote"] = behavior
                item["reason"] = "metadata만 인용하는 합성 부정 사례"
        return body

    agents.set("cv-choice-review", metadata_only)
    with pytest.raises(ValueError, match="creator.*evidence"):
        run_s3_variants(ctx, cid)


def test_creator_selected_behaviors_survive_choice_planning_and_requirements(tmp_path):
    ctx, _, cid = setup_choices(tmp_path)
    first = load_latest_seed(ctx, cid)
    selected = resolve_traits(["P01-T1"])
    write_seed(ctx, cid, dump(first), trait_ids=[selected[0].traitId])
    out = run_s3_variants(ctx, cid)
    rows = read_json(out / "variants.json")["candidates"]
    assert all(row["selectedTraits"] == [dump(selected[0])] for row in rows)
    requirements = read_json(out / "requirements.json")["requirements"]
    assert any(
        r["field"] == "selectedTraits"
        and r["quote"] == selected[0].behavior
        and r["kind"] == "fixed"
        for r in requirements
    )


def test_final_choice_voice_prompt_preserves_creator_traits_even_if_writer_omits_them(tmp_path):
    ctx, _, cid = choice_voice_case(tmp_path, selected_ids=["P02-T1"])
    trait = run_s7(ctx, cid)
    out = run_s8(ctx, cid, [])
    pair = read_json(out / "prompt-pair.json")
    behavior = resolve_traits(["P02-T1"])[0].behavior
    assert behavior in pair["long"]["text"]
    assert "제작자가 추가한 성향" not in pair["long"]["text"]
    assert "[PERSONA / DISPOSITION]" in pair["long"]["text"]
    assert (
        behavior
        in canonical_plan(
            validate(
                "character-plan-v2",
                read_json(
                    ctx.character_dir(cid)
                    / "s3-plan"
                    / ctx.state(cid).stage("s3").currentRev
                    / "plan.json"
                ),
            ),
            ctx.character_dir(cid)
            / "s3-plan"
            / ctx.state(cid).stage("s3").currentRev
            / "plan.json",
        )["plan"]["selectedTraits"][0]["behavior"]
    )
    assert (trait.parent / "blueprint.json").is_file()


def test_legacy_assembler_also_keeps_selected_traits_in_both_lengths():
    from character_factory_poc.stages.s8_prompts.build import assemble
    from tests.support.flow import sample_plan_v2

    raw = sample_plan_v2("synthetic")
    selected = resolve_traits(["P02-T1"])
    raw["selectedTraits"] = [dump(x) for x in selected]
    plan = validate("character-plan-v2", raw)
    for generated in ["자기 이야기도 적당히 나눈다.", "자기 이야기를 나눈다."]:
        body = {"PERSONA / DISPOSITION": generated}
        text = assemble(list(body), body, plan.name, "", creator_plan=plan)
        assert generated in text
        assert selected[0].behavior in text
