"""Full coverage, counterevidence and resumable extraction, entirely synthetic."""

from types import SimpleNamespace

import pytest

from character_factory_poc.common.store import read_json
from character_factory_poc.stages.s8_prompts import evidence_full_pipeline as full


def card(refs):
    return dict(
        section="VOICE",
        trigger="친구가 이미 합의한 사항을 다시 확인할 때",
        first="가능 여부를 짧게 확인한다.",
        shift="새 조건이 있을 때만 덧붙인다.",
        stop="합의가 유지되면 차례를 넘긴다.",
        limit="이유를 요청하면 설명을 생략하지 않는다.",
        evidence=refs,
        rule="짧게 확인한다.",
    )


def source():
    rs = [
        dict(
            id=str(i),
            unit=["t", str(i)],
            context="가상 질문 " + str(i),
            target="합성 응답 " + str(i),
            next=None,
            followup=None,
            history=[],
        )
        for i in range(3)
    ]
    return dict(
        records=rs,
        chunks=[dict(id=f"c{i}", recordIds=[str(i)], segments=[]) for i in range(3)],
        coverage=dict(complete=True),
        stats=dict(sampled_records=3),
        holdoutIds=[],
    )


def packet():
    return dict(
        role="모티브 AI다.",
        scene="친구 메신저",
        facts="직업 없음",
        trainIds=["0", "1", "2"],
        holdoutIds=[],
        sections=[],
        formatVersion="evidence-conditions-v2",
    )


def test_all_chunks_are_discovered_and_rechecked_and_conditions_survive(tmp_path, monkeypatch):
    calls = []

    def call(ctx, cid, folder, budget, phase, key, payload):
        calls.append((phase, key))
        if phase == "discover":
            return {"observations": [card(payload["chunk"]["recordIds"])]}, "fake"
        if phase == "consolidate":
            return {"sections": [card(["0", "1"])]}, "fake"
        return {
            "findings": [
                dict(
                    claimId="claim-01",
                    support=payload["chunk"]["recordIds"],
                    counter=[],
                    unclear=[],
                    note="해당 조건에서 확인됨",
                )
            ]
        }, "fake"

    monkeypatch.setattr(full, "_call", call)
    ctx = SimpleNamespace(config=SimpleNamespace(stage=lambda _: {}))
    text, assembly = full.build_full(ctx, "x", packet(), source(), {}, tmp_path, None)
    assert sum(p == "discover" for p, _ in calls) == 3
    assert sum(p == "audit" for p, _ in calls) == 3
    assert "이유를 요청하면 설명을 생략하지 않는다." in text
    review = read_json(tmp_path / "evidence-review.json")
    assert review["coverage"]["complete"] and review["auditCoverage"]["complete"]
    assert len(review["cards"]) == 1 and assembly["status"] == "AWAITING_HUMAN"


def test_counterexample_blocks_candidate_instead_of_silently_editing_it(tmp_path, monkeypatch):
    def call(ctx, cid, folder, budget, phase, key, payload):
        if phase == "discover":
            return {"observations": [card(payload["chunk"]["recordIds"])]}, "fake"
        if phase == "consolidate":
            return {"sections": [card(["0", "1"])]}, "fake"
        rid = payload["chunk"]["recordIds"][0]
        return {
            "findings": [
                dict(
                    claimId="claim-01",
                    support=[] if rid == "2" else [rid],
                    counter=["2"] if rid == "2" else [],
                    unclear=[],
                    note="반례 존재" if rid == "2" else "조건부 지지",
                )
            ]
        }, "fake"

    monkeypatch.setattr(full, "_call", call)
    ctx = SimpleNamespace(config=SimpleNamespace(stage=lambda _: {}))
    with pytest.raises(ValueError, match="후보"):
        full.build_full(ctx, "x", packet(), source(), {}, tmp_path, None)
    assert not (tmp_path / "long.md").exists()
    assert read_json(tmp_path / "evidence-review.json")["held"][0]["counter"] == ["2"]


def test_audit_must_cover_each_claim_and_cannot_reference_other_chunk():
    chunk = dict(id="c", recordIds=["a"])
    claims = [dict(id="claim-01", card=card(["a"]))]
    with pytest.raises(ValueError):
        full.validate_findings({"findings": []}, claims, chunk)
    with pytest.raises(ValueError):
        full.validate_findings(
            {
                "findings": [
                    dict(
                        claimId="claim-01",
                        support=["outside"],
                        counter=[],
                        unclear=[],
                        note="조건 확인",
                    )
                ]
            },
            claims,
            chunk,
        )


def test_incomplete_source_is_blocked_before_any_paid_call(tmp_path, monkeypatch):
    s = source()
    s["coverage"]["complete"] = False
    monkeypatch.setattr(
        full, "_call", lambda *args: pytest.fail("paid call before coverage checked")
    )
    with pytest.raises(ValueError, match="전체|누락"):
        full.build_full(None, "x", packet(), s, {}, tmp_path, None)


def test_actual_v2_s8_g6_and_preview_keep_full_conditions(tmp_path):
    import json

    from character_factory_poc.common.demo_chat import Scene
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from character_factory_poc.stages.s8_prompts.evidence_pipeline import verify_review
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v2"

    def answer(req):
        p = json.loads(req.messages[1].content)
        if p["phase"] == "discover":
            return {"observations": [card(p["chunk"]["recordIds"])]}
        if p["phase"] == "consolidate":
            return {"sections": [p["observations"][0]["observations"][0]]}
        return {
            "findings": [
                dict(
                    claimId=c["id"],
                    support=p["chunk"]["recordIds"],
                    counter=[],
                    unclear=[],
                    note="조건과 일치",
                )
                for c in p["claims"]
            ]
        }

    # Replace the queued legacy response, leaving already completed setup intact.
    model.add("AGENT", answer)
    model.add("AGENT", answer)
    model.add("AGENT", answer)
    folder = run_s8(ctx, cid, [])
    r = verify_review(ctx, cid, folder)
    assert r["schemaVersion"] == "evidence-review-v2"
    assert (
        "이유를 요청하면 설명을 생략하지 않는다."
        in Scene.read(ctx.character_dir(cid), review_preview=True).compose()
    )
    assert not (folder / "example-turns.json").exists()


def test_cached_request_hash_is_independent_of_model_key_order(tmp_path):
    from character_factory_poc.providers.fake import FakeTextModel

    model = FakeTextModel(responses={"AGENT": {"sections": []}})
    ctx = SimpleNamespace(text_model=lambda *args: model)
    first = {"observations": [{"z": "끝", "a": "처음"}]}
    second = {"observations": [{"a": "처음", "z": "끝"}]}
    full._call(ctx, "c", tmp_path, None, "consolidate", "all", first)
    full._call(ctx, "c", tmp_path, None, "consolidate", "all", second)
    assert len(model.requests) == 1


def test_invalid_audit_response_is_archived_and_retried(tmp_path):
    from character_factory_poc.providers.fake import FakeTextModel

    good = {
        "findings": [
            dict(claimId="claim-01", support=["a"], counter=[], unclear=[], note="조건을 만족함")
        ]
    }
    model = FakeTextModel(responses={"AGENT": [{"findings": []}, good]})
    ctx = SimpleNamespace(text_model=lambda *args: model)
    payload = dict(claims=[dict(id="claim-01", card=card(["a"]))], chunk=dict(recordIds=["a"]))
    result, _ = full._call(ctx, "c", tmp_path, None, "audit", "c1", payload)
    assert result == good and len(model.requests) == 2
    assert list((tmp_path / "analysis/rejected").glob("*.json"))


def test_rework_survives_interruption_without_repeating_completed_chunks(tmp_path):
    import json

    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    run_s8(ctx, cid, [])
    approve_gate(
        ctx,
        cid,
        "G6",
        dict(
            decision="REQUEST_CHANGES",
            reviewer="test",
            reasons="조건 보존",
            requestedChanges=[dict(field="long", note="전체 원문과 조건 보존")],
        ),
    )
    from character_factory_poc.pipeline.orchestrator import RunOptions
    from character_factory_poc.pipeline.rework import prepare_rework
    ctx.config.rework["normalize"] = False
    prepare_rework(ctx, cid, "s8", RunOptions())
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v2"
    fail = [True]
    seen = []

    def answer(req):
        p = json.loads(req.messages[1].content)
        seen.append(p)
        assert p["editorRevision"]["targets"]
        if p["phase"] == "discover":
            return {"observations": [card(p["chunk"]["recordIds"])]}
        if p["phase"] == "consolidate":
            if fail.pop() if fail else False:
                raise RuntimeError("transport test")
            return {"sections": p["observations"][0]["observations"]}
        return {
            "findings": [
                dict(
                    claimId=c["id"],
                    support=p["chunk"]["recordIds"],
                    counter=[],
                    unclear=[],
                    note="지지",
                )
                for c in p["claims"]
            ]
        }

    model.add("AGENT", answer)
    with pytest.raises(RuntimeError):
        run_s8(ctx, cid, [])
    first_rev = ctx.state(cid).stage("s8").currentRev
    folder = run_s8(ctx, cid, [])
    assert folder.name == first_rev
    assert sum(p["phase"] == "discover" for p in seen) == 1


def test_user_only_speech_is_also_checked_for_copying():
    c = card(["0", "1"])
    c["first"] = "아주특이한개인대화원문문장을그대로복사한다"
    with pytest.raises(ValueError, match="copied"):
        full._cards(
            {"sections": [c]},
            "sections",
            10,
            packet(),
            source()["records"],
            ["0", "1"],
            extra_speech=[c["first"]],
        )
