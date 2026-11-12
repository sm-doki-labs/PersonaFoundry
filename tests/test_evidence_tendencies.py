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
        if phase == "tendency-consolidate":
            assert all("heldClaims" not in o for o in p["observations"])
        if phase in ["tendency-discover", "tendency-consolidate"]:
            c = {k: v for k, v in claim().items() if k != "id"}
            c.update(dimension="response", evidence=p["allowedIds"][:2])
            excluded = dict(c, realization="상대에게 '합성 대사입니다'라고 답한다.")
            return {
                "claims": [c],
                "heldClaims": [dict(claim=excluded, reason="예시 대사 보류")],
            }, "fake"
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
    # Small sources cap the conversation minimum at the conversations they have.
    assert review["supportRule"]["requiredConversations"] == 3
    decision = read_json(folder / "evidence-tendency-decisions.json")[0]
    assert decision["retained"] and decision["support"]["conversations"] == 3
    excluded = review["excludedClaims"]
    assert len(excluded) == sum(
        p in {"tendency-discover", "tendency-consolidate"} for p, _ in phases
    )
    assert {x["phase"] for x in excluded} == {"tendency-discover", "tendency-consolidate"}
    assert all(x["reason"] == "예시 대사 보류" and x["chunkId"] for x in excluded)
    assert "합성 대사입니다" not in (folder / "long.md").read_text()
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


def test_blank_audit_note_is_marked_not_rejected():
    m = module()
    p = {"claims": [claim()], "chunk": chunk(), "targets": m.targets(chunk())}
    out = {"findings": [dict(claimId="tendency-01", items=[], note="")]}
    m.validate_transport("tendency-audit", out, p)
    assert out["findings"][0]["note"] == m.BLANK_NOTE and out["findings"][0]["items"] == []
    missing = {"findings": []}
    with pytest.raises(ValueError, match="누락"):
        m.validate_transport("tendency-audit", missing, p)


def test_quoted_discovery_claim_is_held_without_dropping_the_chunk():
    """발화를 인용한 후보 하나는 보류하고 나머지로 진행한다. 형식 오류는 여전히 거절한다(D-0186)."""
    m = module()
    p = {"allowedIds": ["s1", "s2"]}
    good = {k: v for k, v in claim().items() if k != "id"}
    quoted = dict(good, realization="답을 시작할 때 '일단은'을 앞에 둔다.")
    out = {"claims": [good, quoted]}
    m.validate_transport("tendency-discover", out, p)
    assert out["claims"] == [good]
    assert out["heldClaims"][0]["claim"] == quoted
    assert "dialogue/example" in out["heldClaims"][0]["reason"]
    unchanged = deepcopy(out)
    m.validate_transport("tendency-discover", out, p)  # 저장본을 다시 읽어도 같다
    assert out == unchanged
    outside = dict(good, evidence=["s9"])
    with pytest.raises(ValueError, match="허용 원문 밖"):
        m.validate_transport("tendency-discover", {"claims": [good, outside]}, p)
    with pytest.raises(ValueError, match="범주"):
        m.validate_transport("tendency-discover", {"claims": [dict(quoted, section="UNKNOWN")]}, p)


def _half(ids, unit_of, variation=()):
    return dict(
        support=list(ids),
        supportUnits=len({unit_of[r] for r in ids}),
        variation=list(variation),
        outside=[],
        unclear=[],
    )


def test_thin_support_is_held_by_conversation_count_and_share():
    m = module()
    units = {f"s{i}": ("t", f"c{i}") for i in range(40)}
    rule = m.support_rule({}, 160)
    assert (rule["requiredConversations"], rule["minShare"]) == (8, 0.5)
    # 5 responses from 5 conversations: the shape of a narrow one-off register card.
    narrow = m.support_stats(
        _half(["s1", "s2", "s3", "s4"], units, ["s10", "s11"]),
        _half(["s5"], units, ["s12", "s13"]),
        units,
    )
    assert (narrow["responses"], narrow["conversations"], narrow["applicable"]) == (5, 5, 9)
    reason = m.thin_support(narrow, rule)
    assert "대화 수" in reason and "5개(기준 8개)" in reason and "5/9건" in reason
    broad = m.support_stats(
        _half([f"s{i}" for i in range(14)], units),
        _half(["s20", "s21", "s22", "s23"], units),
        units,
    )
    assert broad["conversations"] == 18 and m.thin_support(broad, rule) is None
    contested = m.support_stats(
        _half([f"s{i}" for i in range(8)], units, [f"s{i}" for i in range(20, 31)]),
        _half(["s32", "s33"], units),
        units,
    )
    assert contested["conversations"] == 10 and contested["share"] < 0.5
    assert "지지 비율" in m.thin_support(contested, rule)
    # A small source cannot demand more conversations than it has.
    assert m.support_rule({}, 3)["requiredConversations"] == 3
    custom = m.support_rule({"evidence_min_support": {"conversations": 4, "share": 0}}, 160)
    assert m.thin_support(narrow, custom) is None
    for bad in [{"conversations": 0}, {"share": 1.5}, {"share": True}, {"count": 3}, 8]:
        with pytest.raises(ValueError, match="evidence_min_support"):
            m.support_rule({"evidence_min_support": bad}, 160)


def test_native_build_holds_thin_cards_with_numbers_in_review(tmp_path, monkeypatch):
    from character_factory_poc.common.store import read_json
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from tests.test_evidence_pipeline import ready

    ctx, _, cid = ready(tmp_path)
    m = module()
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v4"
    base = {k: v for k, v in claim().items() if k != "id"}
    functions = ["판단의 근거 설명", "정정 요청에 대한 반박"]

    def fake(ctx, cid, folder, budget, phase, key, p):
        if phase in ["tendency-discover", "tendency-consolidate"]:
            ev = p["allowedIds"][:2]
            claims = [dict(base, dimension="response", function=f, evidence=ev) for f in functions]
            return {"claims": claims}, "fake"
        ts = {t["id"]: t for seg in p["chunk"]["segments"] for t in seg["turns"]}
        items = [
            dict(
                responseTurnId=rid,
                conditionTurnId=t["precedingUserIds"][-1],
                conditionQuote=ts[t["precedingUserIds"][-1]]["text"],
                responseQuote=ts[rid]["text"],
                applicability="yes",
                functionMatch="present",
                formMatch="present",
                reason="합성 검증",
            )
            for rid, t in p["targets"].items()
        ]
        out = {"findings": [dict(claimId=c["id"], items=items, note="합성") for c in p["claims"]]}
        m.validate_phase(phase, out, p)
        return out, "fake"

    # The fixture has 3 one-response conversations; report it as a 30-conversation source so
    # the default minimum of 8 applies, as it does for a real chat source.
    real = m.support_rule
    monkeypatch.setattr(m, "support_rule", lambda cfg, n, default: real(cfg, n * 10, default))
    monkeypatch.setattr(m, "call", fake)
    with pytest.raises(ValueError, match="반복 근거"):
        run_s8(ctx, cid, [])
    folder = ctx.character_dir(cid) / "s8-prompts/pv1"
    review = read_json(folder / "evidence-review.json")
    assert review["status"] == "HELD" and review["cards"] == []
    assert review["supportRule"]["requiredConversations"] == 8
    assert [h["claim"]["function"] for h in review["held"]] == functions
    for h in review["held"]:
        assert h["support"]["conversations"] == 3 and h["support"]["share"] == 1.0
        assert h["reason"].startswith("지지 근거가 얇다(대화 수 미달)")
        assert "3개(기준 8개)" in h["reason"]
    assert not (folder / "evidence-packet.json").exists()
