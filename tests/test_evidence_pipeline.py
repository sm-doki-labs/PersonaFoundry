"""Synthetic source -> standard S8 -> explicit G6 -> demo, with no paid calls."""

import json

import pytest

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.demo_chat import Scene
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.approve import approve_gate, approve_text_gate
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from tests.support.web_gates import trait_sheet_for
from tests.test_twin_s3 import CANARY, _ready


def candidate(req):
    data = json.loads(req.messages[1].content)
    phase = data.get("phase")
    if phase and phase.startswith("tendency-"):
        usage = "usageAxis" in req.messages[0].content
        if phase == "tendency-consolidate":
            return {"claims": data["observations"][0]["claims"]}
        if phase == "tendency-discover":
            return {
                "claims": [
                    dict(
                        section="VOICE",
                        function="판단 근거 전달",
                        dimension="response",
                        trigger="상대가 이유를 물었을 때",
                        realization="인과 연결어미로 사유를 서술한다.",
                        linguisticLevel="syntax",
                        exclusion="상대가 이해를 표시한 수신에는 확대하지 않는다.",
                        observability="prior_context",
                        evidence=data["allowedIds"],
                        **({"usageAxis": "other"} if usage else {}),
                    )
                ]
            }
        ts = {t["id"]: t for seg in data["chunk"]["segments"] for t in seg["turns"]}
        items = []
        for rid, target in data["targets"].items():
            uid = target["precedingUserIds"][-1]
            items.append(
                dict(
                    responseTurnId=rid,
                    conditionTurnId=uid,
                    conditionQuote=ts[uid]["text"],
                    responseQuote=ts[rid]["text"],
                    applicability="yes",
                    functionMatch="present",
                    formMatch="present",
                    reason="합성 근거",
                    **({"conditionBasis": "explicit_user_act"} if usage else {}),
                )
            )
        return {
            "findings": [
                dict(claimId=c["id"], items=items, note="합성 대조") for c in data["claims"]
            ]
        }
    if phase and phase.startswith("atomic-"):
        if phase == "atomic-consolidate":
            return {"atoms": data["observations"][0]["atoms"]}
        if phase == "atomic-refine":
            return {"atoms": [{k: v for k, v in c.items() if k != "id"} for c in data["claims"]]}
        if phase != "atomic-discover":
            return {
                "findings": [
                    dict(
                        atomId=c["id"],
                        items=[
                            dict(
                                recordId=r,
                                applicable="yes",
                                behavior="support",
                                triggerReason="질문이 앞에 있음",
                                behaviorReason="현재 질문에 답함",
                            )
                            for r in data["chunk"]["recordIds"]
                        ],
                        note="합성 근거",
                    )
                    for c in data["claims"]
                ]
            }
        return {
            "atoms": [
                dict(
                    section="VOICE",
                    function="응답",
                    dimension="response",
                    trigger="상대가 질문했을 때",
                    behavior="현재 질문의 내용을 받아 답한다.",
                    exclusion="질문이 없는 장면에는 일반화하지 않는다.",
                    evidence=data["chunk"]["recordIds"],
                )
            ]
        }
    if phase == "consolidate":
        return {"sections": data["observations"][0]["observations"]}
    if phase == "audit":
        return {
            "findings": [
                dict(
                    claimId=c["id"],
                    support=data["chunk"]["recordIds"],
                    counter=[],
                    unclear=[],
                    note="조건과 일치",
                )
                for c in data["claims"]
            ]
        }
    refs = (
        data["chunk"]["recordIds"]
        if phase == "discover"
        else [r["id"] for r in data["records"][:2]]
    )
    return {
        ("observations" if phase == "discover" else "sections"): [
            dict(
                section="VOICE",
                trigger="상대가 다음 행동을 정하려고 할 때",
                first="관련 선택을 먼저 짧게 제시한다.",
                shift="이유를 물으면 판단의 조건을 설명한다.",
                stop="상대가 수락하면 추가 질문 없이 마친다.",
                limit="진지한 감정 표현에 확대하지 않는다.",
                evidence=refs,
                rule=(
                    "행동을 정하는 질문에는 선택을 먼저 제시하며, "
                    "이유 요청이 있을 때만 판단 조건을 풀어 설명한다."
                ),
            )
        ]
    }


def ready(tmp_path):
    ctx, model, cid = _ready(tmp_path)
    ctx.config.stages.setdefault("s8", {})["motif_compiler"] = "evidence-v1"
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"})
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)
    model.add("AGENT", candidate)
    return ctx, model, cid


def test_legacy_pipeline_compiles_reviewed_evidence_without_examples(tmp_path):
    ctx, model, cid = ready(tmp_path)
    folder = run_s8(ctx, cid, [])
    pair = read_json(folder / "prompt-pair.json")
    review = read_json(folder / "evidence-review.json")
    packet = read_json(folder / "evidence-packet.json")
    assert pair["systemRulesRef"] == "builtin:evidence-pipeline-v1"
    assert len(pair["sections"]) == 8
    assert packet["facts"] in pair["long"]["text"]
    assert "긍정도 부정도 단정하지 않는다" in pair["long"]["text"]
    assert pair["short"] == pair["long"]
    assert review["cards"] and review["status"] == "AWAITING_HUMAN"
    assert not (folder / "example-turns.json").exists()
    assert CANARY not in str(review)
    assert CANARY not in str(
        [m.content for r in model.requests if r.stage == "s8" for m in r.messages]
    )
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    with pytest.raises(ValueError, match="근거|검토"):
        approve_text_gate(ctx, cid, "G6")
    with pytest.raises(ValueError, match="근거|검토"):
        approve_gate(ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test"})
    approve_gate(
        ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    )
    version = read_json(folder / "persona-version.json")
    assert version["long"] == pair["long"]
    scene = Scene.read(ctx.character_dir(cid))
    assert scene.compose() == pair["long"]["text"].rstrip("\n")
    assert len(scene.opening()) == 1
    assert sha256_text(pair["long"]["text"]) == pair["long"]["sha256"]


@pytest.mark.parametrize("target", ["corpus", "facts", "scene", "packet", "long"])
def test_g6_rejects_stale_or_edited_inputs(tmp_path, target):
    ctx, _, cid = ready(tmp_path)
    folder = run_s8(ctx, cid, [])
    if target == "scene":
        ctx.config.stages.setdefault("s8", {})["evidence_scene"] = "다른 관계와 장면"
    elif target == "facts":
        path = ctx.character_dir(cid) / "s0-source/sp1/source-pack.json"
        data = read_json(path)
        data["knownFacts"]["age"] = "55"
        path.write_text(json.dumps(data))
    elif target == "corpus":
        path = ctx.character_dir(cid) / "s0-source/sp1/corpus.jsonl"
        path.write_text(path.read_text() + "\n")
    elif target == "packet":
        path = folder / "evidence-packet.json"
        data = read_json(path)
        data["sections"][0]["rule"] = "변조한 내용이다."
        path.write_text(json.dumps(data))
    else:
        (folder / "long.md").write_text("변조한 내용이다.")
    with pytest.raises(ValueError):
        approve_gate(
            ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
        )
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    assert not (folder / "persona-version.json").exists()


def test_all_invalid_candidates_are_held_without_fallback(tmp_path):
    ctx, model, cid = ready(tmp_path)

    def invalid(req):
        out = candidate(req)
        out["sections"][0]["evidence"] = ["unknown"]
        return out

    model.add("AGENT", invalid)
    with pytest.raises(ValueError, match="근거|후보"):
        run_s8(ctx, cid, [])
    folder = ctx.character_dir(cid) / "s8-prompts/pv1"
    assert read_json(folder / "evidence-review.json")["held"]
    assert not (folder / "long.md").exists()
    assert ctx.state(cid).stage("s8").status == "CHECK_FAILED"


def test_rework_creates_new_revision_and_reject_does_not_require_ack(tmp_path):
    ctx, model, cid = ready(tmp_path)
    first = run_s8(ctx, cid, [])
    original = (first / "long.md").read_bytes()
    approve_gate(
        ctx,
        cid,
        "G6",
        {
            "decision": "REQUEST_CHANGES",
            "reviewer": "test",
            "reasons": "조건을 좁혀 주세요",
            "requestedChanges": [{"field": "long", "note": "조건을 좁혀 주세요"}],
        },
    )

    def revised(req):
        out = candidate(req)
        out["sections"][0]["rule"] += " 상대가 선택을 맡긴 경우에 한정한다."
        return out

    model.add("AGENT", revised)
    second = run_s8(ctx, cid, [])
    assert second.name == "pv2" and (first / "long.md").read_bytes() == original
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"


def test_unapproved_demo_is_blocked_but_review_samples_can_preview(tmp_path):
    from character_factory_poc.common.demo_chat import NotReady

    ctx, _, cid = ready(tmp_path)
    folder = run_s8(ctx, cid, [])
    with pytest.raises(NotReady, match="검토|승인"):
        Scene.read(ctx.character_dir(cid)).opening()
    assert Scene.read(ctx.character_dir(cid), review_preview=True).compose() == (
        folder / "long.md"
    ).read_text().rstrip("\n")


def test_approved_demo_rejects_changed_review_and_source(tmp_path):
    from character_factory_poc.common.demo_chat import NotReady

    ctx, _, cid = ready(tmp_path)
    folder = run_s8(ctx, cid, [])
    approve_gate(
        ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    )
    (folder / "evidence-review.json").write_text("{}")
    with pytest.raises(NotReady):
        Scene.read(ctx.character_dir(cid)).opening()


def test_examples_option_rejected_before_model_call(tmp_path):
    ctx, model, cid = ready(tmp_path)
    count = len(model.requests)
    ctx.config.stages.setdefault("s8", {})["example_turns"] = 3
    with pytest.raises(ValueError, match="예시"):
        run_s8(ctx, cid, [])
    assert len(model.requests) == count


def test_interrupted_extraction_resumes_without_another_model_call(tmp_path, monkeypatch):
    from character_factory_poc.stages.s8_prompts import evidence_pipeline as ep

    ctx, model, cid = ready(tmp_path)
    original = ep.compile_prompt

    def interrupt(packet):
        if packet["sections"]:
            raise KeyboardInterrupt()
        return original(packet)

    monkeypatch.setattr(ep, "compile_prompt", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_s8(ctx, cid, [])
    calls = len(model.requests)
    monkeypatch.setattr(ep, "compile_prompt", original)
    folder = run_s8(ctx, cid, [])
    assert folder.name == "pv1"
    assert len(model.requests) == calls


@pytest.mark.parametrize("quoted", ['"작은 책방"', "'작은 책방'", "‘작은 책방’"])
def test_quotes_in_approved_facts_survive_without_becoming_dialogue_examples(tmp_path, quoted):
    from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt
    from tests.test_evidence_compiler import packet

    data = packet()
    data["facts"] = f"직업: {quoted} 운영자.\n상호는 그대로 보존한다."
    assert "[FACTS]\n" + data["facts"] in compile_prompt(data)


def test_export_loader_rejects_approved_source_drift(tmp_path):
    from character_factory_poc.stages.s11_release.package import load_persona

    ctx, _, cid = ready(tmp_path)
    folder = run_s8(ctx, cid, [])
    approve_gate(
        ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    )
    assert load_persona(ctx, cid)[2].long.text == (folder / "long.md").read_text()
    ctx.config.stages.setdefault("s8", {})["evidence_scene"] = "장면을 새로 바꾼다."
    with pytest.raises(ValueError, match="장면|달라"):
        load_persona(ctx, cid)


def test_marker_edit_cannot_skip_evidence_approval(tmp_path):
    ctx, _, cid = ready(tmp_path)
    folder = run_s8(ctx, cid, [])
    path = folder / "prompt-pair.json"
    pair = read_json(path)
    pair["systemRulesRef"] = "builtin:motif-assembler-v3"
    path.write_text(json.dumps(pair))
    with pytest.raises(ValueError, match="근거|검토"):
        approve_gate(ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test"})


def test_new_evidence_revision_refreshes_chapter_samples(tmp_path, monkeypatch):
    from character_factory_poc.common import demo_chat
    from character_factory_poc.pipeline.orchestrator import RunLog, RunOptions, _step
    from character_factory_poc.stages.s8_prompts.chapter_start import run_s8c
    from tests.test_chapter_start import _start

    ctx, model, cid = ready(tmp_path)
    run_s8(ctx, cid, [])
    monkeypatch.setattr(demo_chat, "run_samples", lambda ctx, cid: None)
    model.add("AGENT", lambda req: _start().model_dump() | {"characterId": cid})
    run_s8c(ctx, cid)
    approve_gate(
        ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    )
    model.add("AGENT", candidate)
    run_s8(ctx, cid, [])
    model.add("AGENT", lambda req: _start().model_dump() | {"characterId": cid})
    runners = {"s8c": lambda: run_s8c(ctx, cid)}
    _step(ctx, cid, "s8c", RunOptions(until="s8c"), runners, RunLog(), auto_review=True)
    assert ctx.state(cid).stage("s8c").currentRev == "cs2"
    inputs = read_json(ctx.character_dir(cid) / "s8-chapters/cs2/inputs.json")
    assert inputs["promptRevision"] == "pv2"
    calls = len(model.requests)
    _step(ctx, cid, "s8c", RunOptions(until="s8c"), runners, RunLog(), auto_review=True)
    assert len(model.requests) == calls


@pytest.mark.parametrize("quoted", ["'괜찮아'", "‘괜찮아’", "「괜찮아」"])
def test_short_quoted_reply_is_not_a_linguistic_rule(quoted):
    from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt
    from tests.test_evidence_compiler import packet

    data = packet()
    data["sections"][0]["rule"] = "상대가 힘들다고 하면 " + quoted + "라고 답한다."
    with pytest.raises(ValueError, match="example"):
        compile_prompt(data)


@pytest.mark.parametrize(
    "template,expected", [("FAN_CALL", "팬과 통화"), ("FAMILY_CALL", "가족과 통화")]
)
def test_target_scene_precedes_source_file_format(tmp_path, template, expected):
    ctx, model, cid = _ready(tmp_path, template=template)
    ctx.config.stages.setdefault("s8", {})["motif_compiler"] = "evidence-v1"
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"})
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)
    model.add("AGENT", candidate)
    folder = run_s8(ctx, cid, [])
    assert expected in read_json(folder / "evidence-packet.json")["scene"]


def test_orchestrator_reports_stale_approved_evidence_instead_of_reusing(tmp_path):
    from character_factory_poc.pipeline.orchestrator import RunLog, RunOptions, _step

    ctx, _, cid = ready(tmp_path)
    run_s8(ctx, cid, [])
    approve_gate(
        ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    )
    source = ctx.character_dir(cid) / "s0-source/sp1/corpus.jsonl"
    source.write_text(source.read_text() + "\n")
    invoked = []
    log = RunLog()
    _step(ctx, cid, "s8", RunOptions(), {"s8": lambda: invoked.append(True)}, log, auto_review=True)
    assert not invoked
    assert "s8" in log.blocked
    assert any("다시" in line or "변경" in line for line in log.steps)


def test_scene_override_is_scoped_to_character(tmp_path):
    from character_factory_poc.stages.s8_prompts.evidence_pipeline import verify_review

    ctx, _, cid = ready(tmp_path)
    ctx.config.stages.setdefault("s8", {})["evidence_scenes"] = {
        cid: "친구끼리 메신저로 이야기한다.",
        "another": "인터뷰어의 질문에 답한다.",
    }
    folder = run_s8(ctx, cid, [])
    assert read_json(folder / "evidence-packet.json")["scene"] == "친구끼리 메신저로 이야기한다."
    ctx.config.stages["s8"]["evidence_scenes"]["another"] = "다른 인터뷰 장면이다."
    verify_review(ctx, cid, folder)
