"""Synthetic regressions for scoped tendencies, never real private chat fixtures."""

import importlib.util
from copy import deepcopy

import pytest

from character_factory_poc.stages.s8_prompts import evidence_pipeline as pipeline


def module():
    name = "character_factory_poc.stages.s8_prompts.evidence_tendencies"
    assert importlib.util.find_spec(name), "conditional tendency compiler is not implemented"
    return __import__(name, fromlist=["*"])


def chunk():
    return {
        "id": "c1",
        "recordIds": ["s1", "s2"],
        "segments": [
            {
                "unit": ["t", "u1"],
                "turns": [
                    {"id": "u1", "speaker": "USER", "text": "어떤 이유로 골랐어?"},
                    {"id": "s1", "speaker": "SUBJECT", "text": "확인할 것이 남아서."},
                    {"id": "u2", "speaker": "USER", "text": "그다음은?"},
                    {"id": "s2", "speaker": "SUBJECT", "text": "기다려야지."},
                ],
            }
        ],
    }


def claim():
    return dict(
        id="tendency-01",
        section="VOICE",
        function="판단의 근거 설명",
        dimension="continuation",
        trigger="앞선 판단에 대해 추가로 설명을 요청할 때",
        realization="연결어미를 생략한 짧은 서술로 조건을 밝힌다.",
        linguisticLevel="syntax",
        exclusion="이미 설명을 이해했다는 수신에는 확대하지 않는다.",
        observability="prior_context",
        evidence=["s1", "s2"],
    )


def item(rid="s2", form="present", app="yes"):
    return dict(
        responseTurnId=rid,
        conditionTurnId="u2",
        conditionQuote="그다음은?",
        responseQuote="기다려야지.",
        applicability=app,
        functionMatch="present",
        formMatch=form,
        reason="추가 요청에 짧게 응답함",
    )


def test_v4_is_routed_in_native_factory():
    from types import SimpleNamespace

    c = SimpleNamespace(config=SimpleNamespace(stage=lambda _: {"motif_compiler": "evidence-v4"}))
    assert pipeline.selected(c)
    assert pipeline.version_for(c) == "evidence-pipeline-v4"


def test_current_response_is_bound_and_cannot_borrow_previous_answer():
    m = module()
    c = chunk()
    p = {"claims": [claim()], "chunk": c, "targets": m.targets(c)}
    good = {"findings": [dict(claimId="tendency-01", items=[item()], note="합성")]}
    m.validate_phase("tendency-audit", good, p)
    bad = deepcopy(good)
    bad["findings"][0]["items"][0]["responseQuote"] = "확인할 것이 남아서."
    with pytest.raises(ValueError):
        m.validate_phase("tendency-audit", bad, p)
    bad = deepcopy(good)
    bad["findings"][0]["items"][0]["conditionTurnId"] = "s1"
    with pytest.raises(ValueError):
        m.validate_phase("tendency-audit", bad, p)


def test_unknown_condition_and_partial_form_never_become_joint_support():
    m = module()
    records = [{"id": "s2", "unit": ["t", "a"]}]

    def audit(it):
        return [{"findings": [dict(claimId="tendency-01", items=[it], note="합성")]}]

    r = m.aggregate(audit(item(form="absent")), [claim()], records)["tendency-01"]
    assert r["support"] == [] and r["variation"] == ["s2"] and r["functionPresent"] == ["s2"]
    r = m.aggregate(audit(item(app="unclear")), [claim()], records)["tendency-01"]
    assert r["support"] == [] and r["unclear"] == ["s2"]


def test_mixed_evidence_survives_as_conditional_option_not_universal_law():
    m = module()
    stats = dict(support=["s1", "s2"], supportUnits=2, variation=["s3"], outside=[], unclear=[])
    assert m.state_for(stats, dict(stats, supportUnits=1)) == "mixed"
    assert m.state_for(stats, dict(stats, supportUnits=0)) == "insufficient"
    card = m.to_card(claim(), ["s1", "s2"], "mixed")
    assert card["trigger"] == claim()["trigger"]
    assert claim()["exclusion"] in card["limit"]
    assert claim()["function"] in card["shift"] and claim()["realization"] in card["shift"]
    assert "가능한" in card["shift"] and "다른 반응" in card["limit"]
    c = claim()
    c["realization"] = "자음 감탄사 ㅇㅎ로 반응한다."
    with pytest.raises(ValueError):
        m.to_card(c, ["s1", "s2"], "mixed")


def test_overlap_conflict_is_preserved_as_unclear_not_support():
    m = module()
    rows = [
        {"findings": [dict(claimId="tendency-01", items=[item(app=app)], note="합성")]}
        for app in ["yes", "no"]
    ]
    r = m.aggregate(rows, [claim()], [{"id": "s2", "unit": ["t", "a"]}])["tendency-01"]
    assert r["support"] == [] and r["unclear"] == ["s2"] and r["conflicts"] == ["s2"]


def test_native_build_retains_conditions_and_rejects_analysis_tampering(tmp_path, monkeypatch):
    from character_factory_poc.common.demo_chat import Scene
    from character_factory_poc.common.store import read_json, write_once_json
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    m = module()
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v4"
    # A failed earlier compiler revision must not be overwritten on a version change.
    old = ctx.character_dir(cid) / "s8-prompts/pv1"
    write_once_json(old / "evidence-binding.json", {"compiler": "evidence-pipeline-v3"})
    write_once_json(old / "evidence-intent.json", {"compiler": "evidence-pipeline-v3"})
    state = ctx.state(cid)
    state.transition("s8", "RUNNING", rev="pv1")
    state.transition("s8", "CHECK_FAILED", rev="pv1", error="synthetic previous failure")
    phases = []

    def fake(ctx, cid, folder, budget, phase, key, p):
        phases.append((phase, p))
        if phase in ["tendency-discover", "tendency-consolidate"]:
            c = {k: v for k, v in claim().items() if k != "id"}
            c.update(dimension="response", evidence=p["allowedIds"][:2])
            return {"claims": [c]}, "fake"
        ts = {t["id"]: t for seg in p["chunk"]["segments"] for t in seg["turns"]}
        items = []
        for rid, t in p["targets"].items():
            uid = t["precedingUserIds"][-1]
            items.append(
                dict(
                    responseTurnId=rid,
                    conditionTurnId=uid,
                    conditionQuote=ts[uid]["text"],
                    responseQuote=ts[rid]["text"],
                    applicability="yes",
                    functionMatch="present",
                    formMatch="present",
                    reason="합성 검증",
                )
            )
        out = {"findings": [dict(claimId=c["id"], items=items, note="합성") for c in p["claims"]]}
        m.validate_phase(phase, out, p)
        return out, "fake"

    monkeypatch.setattr(m, "call", fake)
    folder = run_s8(ctx, cid, [])
    assert (
        folder.name == "pv2"
        and read_json(old / "evidence-intent.json")["compiler"] == "evidence-pipeline-v3"
    )
    review = pipeline.verify_review(ctx, cid, folder)
    assert review["schemaVersion"] == "evidence-review-v4"
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    text = Scene.read(ctx.character_dir(cid), review_preview=True).compose()
    for card in review["cards"]:
        for key in ["trigger", "first", "shift", "stop", "limit"]:
            assert card[key] in text
    assert not (folder / "example-turns.json").exists()
    assert [p for p, _ in phases][-1] == "tendency-confirm"
    (folder / "evidence-locked-tendencies.json").write_text("[]")
    with pytest.raises(ValueError):
        pipeline.verify_review(ctx, cid, folder)


def test_bad_citation_is_quarantined_without_losing_other_valid_evidence():
    m = module()
    p = {"claims": [claim()], "chunk": chunk(), "targets": m.targets(chunk())}
    bad = item("s1")
    bad.update(
        conditionTurnId="u2", conditionQuote="그다음은?", responseQuote="확인할 것이 남아서."
    )
    out = {"findings": [dict(claimId="tendency-01", items=[item(), bad], note="합성")]}
    assert hasattr(m, "validate_transport"), "item quarantine is missing"
    m.validate_transport("tendency-audit", out, p)
    assert [i["responseTurnId"] for i in out["findings"][0]["items"]] == ["s2"]
    assert out["findings"][0]["invalidItems"][0]["item"] == bad
    unchanged = deepcopy(out)
    m.validate_transport("tendency-audit", out, p)
    assert unchanged == out
    stats = m.aggregate(
        [out], [claim()], [{"id": "s1", "unit": ["t", "a"]}, {"id": "s2", "unit": ["t", "a"]}]
    )["tendency-01"]
    assert stats["support"] == ["s2"] and stats["invalidCount"] == 1
