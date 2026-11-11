"""Claims must earn their own evidence; discovery cannot inspect confirmation units."""

from copy import deepcopy

import pytest

from character_factory_poc.stages.s8_prompts import evidence_atomic as atom


def source():
    records = [
        dict(
            id=str(i),
            unit=["t", str(i)],
            context="질문",
            target="응답",
            next=None,
            followup=None,
            history=[],
        )
        for i in range(8)
    ]
    segments = [
        dict(
            unit=r["unit"],
            turns=[dict(id=r["id"], speaker="SUBJECT", text=r["target"], messageIds=[r["id"]])],
        )
        for r in records
    ]
    return dict(
        records=records,
        chunks=[dict(id="chunk-1", segments=segments, recordIds=[r["id"] for r in records])],
        coverage=dict(complete=True, includedMessageIds=[r["id"] for r in records]),
    )


def claim():
    return dict(
        id="a1",
        section="VOICE",
        function="수락",
        dimension="response",
        trigger="이미 제안된 일정을 수락할 때",
        behavior="추가 질문 없이 짧게 수락한다.",
        exclusion="일정이 정해지지 않은 협의에는 적용하지 않는다.",
        evidence=["0", "1"],
    )


def finding(rid, applicable="yes", behavior="support"):
    return dict(
        recordId=rid,
        applicable=applicable,
        behavior=behavior,
        triggerReason="수락할 제안이 앞에 있음",
        behaviorReason="짧은 수락으로 끝남",
    )


def test_confirmation_units_never_enter_discovery_even_in_overlapping_chunks():
    s = source()
    s["chunks"].append(deepcopy(s["chunks"][0]) | {"id": "overlap"})
    dev, check, split = atom.partition(s)

    def units(chunks):
        return {tuple(seg["unit"]) for c in chunks for seg in c["segments"]}

    assert units(dev).isdisjoint(units(check))
    assert units(dev) | units(check) == {("t", str(i)) for i in range(8)}
    assert len(units(check)) == 2
    assert split["complete"]


def test_partial_trigger_and_missing_followup_never_count_as_support():
    c = claim()
    c["dimension"] = "continuation"
    rows = [dict(atomId="a1", items=[finding("0"), finding("1", "unclear")], note="맥락 부족")]
    result = atom.aggregate([dict(findings=rows)], [c], source()["records"])["a1"]
    assert result["support"] == []
    assert set(result["unclear"]) == {"0", "1"}


def test_counter_and_unclear_override_duplicate_overlap_support():
    a = dict(atomId="a1", items=[finding("0"), finding("1")], note="지지")
    b = dict(
        atomId="a1",
        items=[finding("0", behavior="counter"), finding("1", behavior="unclear")],
        note="재검토",
    )
    r = atom.aggregate([dict(findings=[a]), dict(findings=[b])], [claim()], source()["records"])[
        "a1"
    ]
    assert not r["support"] and r["counter"] == ["0"] and r["unclear"] == ["1"]


def test_confirmation_failure_cannot_be_repaired_using_confirmation_answers():
    stats = dict(support=["0", "1"], counter=[], unclear=[], supportUnits=2)
    assert atom.eligible(stats, dict(stats, supportUnits=1))
    assert not atom.eligible(stats, dict(stats, counter=["3"]))
    assert not atom.eligible(stats, dict(stats, supportUnits=0))


def test_atomic_compilation_does_not_invent_other_stages():
    card = atom.to_card(claim(), ["0", "1"])
    assert card["first"] == "추가 질문 없이 짧게 수락한다."
    assert card["shift"] == atom.UNOBSERVED and card["stop"] == atom.UNOBSERVED
    assert card["trigger"] == claim()["trigger"] and card["limit"] == claim()["exclusion"]


def test_audit_rejects_missing_claims_and_cross_chunk_sources():
    with pytest.raises(ValueError):
        atom.validate_audit({"findings": []}, [claim()], {"recordIds": ["0"]})
    with pytest.raises(ValueError):
        atom.validate_audit(
            {"findings": [dict(atomId="a1", items=[finding("outside")], note="근거")]},
            [claim()],
            {"recordIds": ["0"]},
        )


def test_atomic_factory_path_requires_review_and_preserves_atomic_conditions(tmp_path):
    from character_factory_poc.common.demo_chat import Scene
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from character_factory_poc.stages.s8_prompts.evidence_pipeline import verify_review
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v3"
    folder = run_s8(ctx, cid, [])
    review = verify_review(ctx, cid, folder)
    assert review["schemaVersion"] == "evidence-review-v3"
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    assert (
        "현재 질문의 내용을 받아 답한다."
        in Scene.read(ctx.character_dir(cid), review_preview=True).compose()
    )
    assert not (folder / "example-turns.json").exists()
    # Detect retained/review artifacts tampering at the real consumer boundary.
    (folder / "evidence-locked-atoms.json").write_text("[]")
    with pytest.raises(ValueError):
        verify_review(ctx, cid, folder)


def test_refined_candidate_is_rechecked_everywhere_before_confirmation(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from character_factory_poc.common.store import read_json
    from tests.test_evidence_full_pipeline import packet

    s = source()
    # Rich synthetic source with observable context and three development units.
    s["stats"] = {}
    p = packet()
    p["trainIds"] = [str(i) for i in range(8)]
    original = {k: v for k, v in claim().items() if k != "id"}
    calls = []

    def fake(ctx, cid, folder, budget, phase, key, payload):
        calls.append((phase, payload))
        if phase in {"atomic-discover", "atomic-consolidate", "atomic-refine"}:
            refs = payload["allowedIds"][:2]
            return {"atoms": [dict(original, evidence=refs)]}, "fake"
        items = [finding(r) for r in payload["chunk"]["recordIds"]]
        if phase == "atomic-audit":
            items[0]["behavior"] = "counter"
        if phase == "atomic-confirm":
            items[0]["behavior"] = "counter"
        return {"findings": [dict(atomId="atom-01", items=items, note="합성 대조")]}, "fake"

    monkeypatch.setattr(atom, "call", fake)
    ctx = SimpleNamespace(config=SimpleNamespace(stage=lambda _: {}))
    with pytest.raises(ValueError, match="독립 확인"):
        atom.build_atomic(ctx, "c", p, s, {}, tmp_path, None)
    phases = [phase for phase, _ in calls]
    assert phases == [
        "atomic-discover",
        "atomic-consolidate",
        "atomic-audit",
        "atomic-refine",
        "atomic-reaudit",
        "atomic-confirm",
    ]
    review = read_json(tmp_path / "evidence-review.json")
    assert review["status"] == "HELD" and not review["cards"]
    assert review["held"][0]["confirmation"]["counter"]
    confirm_ids = set(calls[-1][1]["chunk"]["recordIds"])
    assert not confirm_ids & {
        r["id"] for phase, payload in calls if phase == "atomic-refine" for r in payload["records"]
    }
    assert not (tmp_path / "evidence-packet.json").exists()


def test_atomic_invalid_response_retries_and_cached_valid_result_reuses(tmp_path):
    from types import SimpleNamespace

    from character_factory_poc.providers.fake import FakeTextModel

    good = {"atoms": [{k: v for k, v in claim().items() if k != "id"}]}
    model = FakeTextModel(responses={"AGENT": [{"atoms": [{"bad": "schema"}]}, good]})
    ctx = SimpleNamespace(text_model=lambda *args: model)
    payload = {"allowedIds": ["0", "1"]}
    actual, _ = atom.call(ctx, "c", tmp_path, None, "atomic-discover", "one", payload)
    cached, _ = atom.call(ctx, "c", tmp_path, None, "atomic-discover", "one", payload)
    assert actual == cached == good
    assert len(model.requests) == 2
    assert list((tmp_path / "analysis/rejected").glob("*.json"))


def test_interrupted_cache_cannot_change_behavior_without_detection(tmp_path):
    import json
    from types import SimpleNamespace

    from character_factory_poc.providers.fake import FakeTextModel

    good = {"atoms": [{k: v for k, v in claim().items() if k != "id"}]}
    model = FakeTextModel(responses={"AGENT": good})
    ctx = SimpleNamespace(text_model=lambda *args: model)
    payload = {"allowedIds": ["0", "1"]}
    atom.call(ctx, "c", tmp_path, None, "atomic-discover", "one", payload)
    p = tmp_path / "analysis/atomic-discover-one.json"
    saved = json.loads(p.read_text())
    saved["output"]["atoms"][0]["behavior"] = "완전히 다른 행동을 한다."
    p.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="변경|무결성"):
        atom.call(ctx, "c", tmp_path, None, "atomic-discover", "one", payload)


def test_budget_too_small_blocks_before_any_extraction(tmp_path):
    from types import SimpleNamespace

    from character_factory_poc.common.budget import RunBudget
    from character_factory_poc.common.errors import BudgetExceeded
    from character_factory_poc.providers.fake import FakeTextModel
    from tests.test_evidence_full_pipeline import packet

    model = FakeTextModel(responses={"AGENT": {"atoms": []}})
    budget = RunBudget(
        tmp_path / "budget.json",
        max_calls=1,
        max_tokens=1000000,
        max_cost_usd=20,
        input_rate_per_million=2,
        output_rate_per_million=12,
    )
    ctx = SimpleNamespace(
        config=SimpleNamespace(stage=lambda _: {}), text_model=lambda *args: model
    )
    s = source()
    s["stats"] = {}
    with pytest.raises(BudgetExceeded):
        atom.build_atomic(ctx, "c", packet(), s, {}, tmp_path / "run", budget)
    assert not model.requests


def test_lexical_examples_cannot_enter_final_atomic_card():
    c = claim()
    c["behavior"] = "자음 축약어(ㅇㅎ, ㅇㅇ 등)로 수신한다."
    with pytest.raises(ValueError, match="예시"):
        atom.to_card(c, ["0", "1"])


def test_validation_retry_pool_is_shared_across_chunks(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.stages.s8_prompts import evidence_full_pipeline as full

    monkeypatch.setattr(full, "ATOMIC_RETRIES", 1, raising=False)
    good = {"atoms": [{k: v for k, v in claim().items() if k != "id"}]}
    bad = {"atoms": [{"bad": "schema"}]}
    model = FakeTextModel(responses={"AGENT": [bad, good, bad, good]})
    ctx = SimpleNamespace(text_model=lambda *args: model)
    payload = {"allowedIds": ["0", "1"]}
    atom.call(ctx, "c", tmp_path, None, "atomic-discover", "one", payload)
    with pytest.raises(ValueError, match="재시도"):
        atom.call(ctx, "c", tmp_path, None, "atomic-discover", "two", payload)
    assert len(model.requests) == 3


def test_refinement_may_echo_known_atom_id_but_cannot_add_unknown_metadata():
    raw = {"atoms": [claim()]}
    atom.validate_atoms(raw, {"allowedIds": ["0", "1"], "claims": [claim()]})
    assert "id" not in raw["atoms"][0]
    with pytest.raises(ValueError):
        atom.validate_atoms(
            {"atoms": [dict(claim(), id="invented")]},
            {"allowedIds": ["0", "1"], "claims": [claim()]},
        )


def test_unchanged_scope_cannot_erase_known_counter_on_second_audit():
    c = claim()
    changed = dict(c, behavior="같은 응답을 다른 말로 설명한다.")
    old = {"a1": dict(support=[], counter=["0"], unclear=[], supportUnits=0)}
    new = {"a1": dict(support=["0", "1"], counter=[], unclear=[], supportUnits=2)}
    atom.preserve_counters([c], old, [changed], new, source()["records"])
    assert new["a1"]["counter"] == ["0"] and new["a1"]["support"] == ["1"]
    assert new["a1"]["supportUnits"] == 1
