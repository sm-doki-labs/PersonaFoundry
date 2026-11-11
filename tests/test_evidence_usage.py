"""Synthetic usage-condition coverage, support eligibility, and native compilation."""

import importlib
import importlib.util
from copy import deepcopy
from types import SimpleNamespace

import pytest

from character_factory_poc.stages.s8_prompts import evidence_pipeline as pipeline
from tests.test_evidence_tendencies import chunk, claim, item


def module():
    name = "character_factory_poc.stages.s8_prompts.evidence_usage"
    assert importlib.util.find_spec(name), "usage condition pipeline missing"
    return importlib.import_module(name)


def test_standard_routes_to_pv6_pipeline_and_v5_remains_opt_in():
    c = SimpleNamespace(config=SimpleNamespace(stage=lambda _: {}))
    assert pipeline.version_for(c) == "evidence-pipeline-v4"
    c.config.stage = lambda _: {"motif_compiler": "evidence-v5"}
    assert pipeline.version_for(c) == "evidence-pipeline-v5"


def test_response_derived_condition_is_not_support_and_missing_axes_are_reported():
    m = module()
    c = dict(claim(), usageAxis="intensity")
    p = dict(claims=[c], chunk=chunk(), targets=m.base.targets(chunk()))
    it = dict(item(), conditionBasis="response_derived")
    out = {"findings": [dict(claimId=c["id"], items=[it], note="합성")]}
    m.validate_transport("tendency-audit", out, p)
    stats = m.aggregate([out], [c], [{"id": "s2", "unit": ["t", "u"]}])[c["id"]]
    assert stats["support"] == [] and stats["unclear"] == ["s2"]
    saved = deepcopy(out)
    m.validate_transport("tendency-audit", out, p)
    assert out == saved
    coverage = m.review_fields([dict(claim=c, retained=False, state="insufficient")])[
        "usageCoverage"
    ]
    assert coverage["register"]["status"] == "unobserved"
    assert coverage["intensity"]["status"] == "insufficient"
    assert coverage["ending"]["retained"] == [] and coverage["softening"]["retained"] == []


def test_missing_condition_basis_is_quarantined_not_treated_as_support():
    m = module()
    c = dict(claim(), usageAxis="softening")
    p = dict(claims=[c], chunk=chunk(), targets=m.base.targets(chunk()))
    out = {"findings": [dict(claimId=c["id"], items=[item()], note="합성")]}
    m.validate_transport("tendency-audit", out, p)
    assert out["findings"][0]["items"] == []
    assert out["findings"][0]["invalidItems"][0]["item"] == item()


@pytest.mark.parametrize("axis", ["register", "intensity", "ending", "softening"])
def test_usage_condition_is_rendered_without_sample_words(axis):
    m = module()
    c = dict(claim(), usageAxis=axis)
    card = m.to_card(c, ["s1", "s2"], "mixed")
    assert c["trigger"] == card["trigger"] and c["exclusion"] in card["limit"]
    assert c["realization"] in card["shift"]
    assert m.AXES[axis] in card["shift"]
    c["realization"] = "자음 약어 ㅋㅋ로 답한다."
    with pytest.raises(ValueError):
        m.to_card(c, ["s1"], "mixed")


def test_native_explicit_v5_build_records_usage_and_preserves_old_revision(tmp_path, monkeypatch):
    from character_factory_poc.common.demo_chat import Scene
    from character_factory_poc.common.store import read_json, write_once_json
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v5"
    m = module()
    old = ctx.character_dir(cid) / "s8-prompts/pv1"
    write_once_json(old / "evidence-intent.json", {"compiler": "evidence-pipeline-v4"})
    write_once_json(old / "evidence-binding.json", {"compiler": "evidence-pipeline-v4"})
    state = ctx.state(cid)
    state.transition("s8", "RUNNING", rev="pv1")
    state.transition("s8", "CHECK_FAILED", rev="pv1", error="synthetic")

    def fake(ctx, cid, folder, budget, phase, key, p):
        if phase in ["tendency-discover", "tendency-consolidate"]:
            c = {k: v for k, v in claim().items() if k != "id"}
            c.update(usageAxis="ending", dimension="response", evidence=p["allowedIds"][:2])
            out = {"claims": [c, dict(c, usageAxis="softening")]}
        else:
            ts = {t["id"]: t for s in p["chunk"]["segments"] for t in s["turns"]}
            its = []
            for rid, t in p["targets"].items():
                uid = t["precedingUserIds"][-1]
                its.append(
                    dict(
                        responseTurnId=rid,
                        conditionTurnId=uid,
                        conditionQuote=ts[uid]["text"],
                        responseQuote=ts[rid]["text"],
                        applicability="yes",
                        functionMatch="present",
                        formMatch="present",
                        conditionBasis="explicit_user_act",
                        reason="합성",
                    )
                )
            out = {
                "findings": [
                    dict(claimId=c["id"], items=deepcopy(its), note="합성") for c in p["claims"]
                ]
            }
        m.validate_transport(phase, out, p)
        return out, "fake"

    monkeypatch.setattr(m, "call", fake)
    folder = run_s8(ctx, cid, [])
    review = pipeline.verify_review(ctx, cid, folder)
    assert (
        folder.name == "pv2"
        and read_json(old / "evidence-intent.json")["compiler"] == "evidence-pipeline-v4"
    )
    assert review["schemaVersion"] == "evidence-review-v5"
    assert review["usageCoverage"]["ending"]["retained"]
    assert review["usageCoverage"]["softening"]["status"] == "insufficient"
    assert any("후속" in h["reason"] for h in review["held"])
    scene = Scene.read(ctx.character_dir(cid), review_preview=True)
    assert len(scene.opening()) == 1 and not (folder / "example-turns.json").exists()
    for card in review["cards"]:
        for k in ["trigger", "first", "shift", "stop", "limit"]:
            assert card[k] in scene.compose()
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    (folder / "evidence-usage-coverage.json").write_text("{}")
    with pytest.raises(ValueError):
        pipeline.verify_review(ctx, cid, folder)


def test_softening_needs_a_previous_response_not_just_a_gentle_first_answer():
    m = module()
    c = dict(claim(), usageAxis="softening", dimension="response")
    with pytest.raises(ValueError, match="이전|후속"):
        m.check_eligibility(c)
    c["dimension"] = "continuation"
    m.check_eligibility(c)


def test_invalid_linguistic_category_is_rejected_before_rendering():
    m = module()
    c = {k: v for k, v in claim().items() if k != "id"}
    c.update(usageAxis="register", linguisticLevel="register")
    with pytest.raises(ValueError):
        m.validate_transport("tendency-discover", {"claims": [c]}, {"allowedIds": ["s1", "s2"]})


@pytest.mark.parametrize(
    "change",
    [
        {"responseQuote": "원문에 없는 인용"},
        {"conditionBasis": []},
        {"responseTurnId": []},
        {"conditionTurnId": []},
    ],
)
def test_invalid_usage_item_keeps_every_raw_field_and_survives_cache_recheck(change):
    m = module()
    c = dict(claim(), usageAxis="intensity")
    p = dict(claims=[c], chunk=chunk(), targets=m.base.targets(chunk()))
    raw = dict(item(), conditionBasis="response_derived", **{})
    raw.update(change)
    out = {"findings": [dict(claimId=c["id"], items=[deepcopy(raw)], note="합성")]}
    m.validate_transport("tendency-audit", out, p)
    assert out["findings"][0]["items"] == []
    assert out["findings"][0]["invalidItems"][0]["item"] == raw
    saved = deepcopy(out)
    m.validate_transport("tendency-audit", out, p)
    assert saved == out


def test_duplicate_response_ids_keep_distinct_original_condition_bases():
    m = module()
    c = dict(claim(), usageAxis="intensity")
    p = dict(claims=[c], chunk=chunk(), targets=m.base.targets(chunk()))
    originals = [dict(item(), conditionBasis=b) for b in ["explicit_user_act", "response_derived"]]
    out = {"findings": [dict(claimId=c["id"], items=deepcopy(originals), note="합성")]}
    m.validate_transport("tendency-audit", out, p)
    assert out["findings"][0]["items"] == []
    assert [x["item"] for x in out["findings"][0]["invalidItems"]] == originals


def test_valid_items_of_one_claim_do_not_pollute_validation_of_another():
    m = module()
    claims = [
        dict(claim(), id=f"usage-{i}", usageAxis=a) for i, a in enumerate(["intensity", "register"])
    ]
    p = dict(claims=claims, chunk=chunk(), targets=m.base.targets(chunk()))
    out = {
        "findings": [
            dict(
                claimId=c["id"],
                items=[dict(item(), conditionBasis="explicit_user_act")],
                note="합성",
            )
            for c in claims
        ]
    }
    m.validate_transport("tendency-audit", out, p)
    assert [len(f["items"]) for f in out["findings"]] == [1, 1]


def test_blank_summary_note_does_not_discard_individually_reasoned_evidence():
    m = module()
    c = dict(claim(), usageAxis="intensity")
    p = dict(claims=[c], chunk=chunk(), targets=m.base.targets(chunk()))
    out = {
        "findings": [
            dict(claimId=c["id"], items=[dict(item(), conditionBasis="explicit_user_act")], note="")
        ]
    }
    m.validate_transport("tendency-audit", out, p)
    assert len(out["findings"][0]["items"]) == 1
    assert out["findings"][0]["note"] == ""
    saved = deepcopy(out)
    m.validate_transport("tendency-audit", out, p)
    assert out == saved
