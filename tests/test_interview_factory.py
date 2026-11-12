"""Original interview authoring is selected by the approved scene, not the character name."""

import json

import pytest

from character_factory_poc.common.demo_chat import Scene
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
from character_factory_poc.stages.s8_prompts.evidence_compiler import (
    FACTS_GUARD,
    FACTS_GUARD_CARD,
    NEUTRAL,
    compile_prompt,
)
from character_factory_poc.stages.s8_prompts.evidence_pipeline import (
    full_plan,
    verify_review,
    version_for,
)
from tests.support.interview import interview_author, interview_judge
from tests.support.web_gates import trait_sheet_for
from tests.test_evidence_compiler import packet
from tests.test_twin_s3 import CANARY, _ready


@pytest.mark.parametrize(
    ("scene", "compiler", "interview_setting", "expected"),
    [
        ("INTERVIEW", "evidence-v4", None, "interview-editor-v2"),
        ("FRIEND_CHAT", "evidence-v4", None, "evidence-pipeline-v4"),
        ("INTERVIEW", "evidence-v4", "inherit", "evidence-pipeline-v4"),
        ("INTERVIEW", "evidence-v5", None, "evidence-pipeline-v5"),
    ],
)
def test_approved_scene_selects_interview_authoring(
    tmp_path, scene, compiler, interview_setting, expected
):
    ctx, _, cid = _ready(tmp_path, template=scene)
    cfg = ctx.config.stages.setdefault("s8", {})
    cfg["motif_compiler"] = compiler
    if interview_setting:
        cfg["interview_compiler"] = interview_setting
    assert version_for(ctx, cid) == expected


def test_interview_compiles_only_scoped_guidance_and_keeps_facts():
    value = packet()
    value["formatVersion"] = "interview-editor-v2"
    value["facts"] = "  출처에서 승인한 사실 한 줄.  \n수치나 표현을 재작성하지 않는다."
    value["sections"][0].update(
        scope="LOCAL",
        trigger="판단을 확인할 때",
        first="확인할 수 있는 부분부터 답한다.",
        shift="",
        stop="",
        limit="설명을 요청했다면 필요한 이유를 이어 간다.",
    )
    text = compile_prompt(value)
    assert "\n[FACTS]\n" + value["facts"] + "\n\n[" in text
    assert "판단을 확인할 때" in text
    assert "확인할 수 있는 부분부터 답한다. 설명을 요청했다면 필요한 이유를 이어 간다." in text
    assert "마무리 조건:" not in text and "이어지는 반응:" not in text
    assert text.count("기억이 흐리다는 말로 사건이 있었던 듯 처리하지 않는다.") == 1
    assert value["sections"][0]["rule"] not in text


@pytest.mark.parametrize("retry", [False, True])
def test_interview_source_through_g6_and_demo(tmp_path, retry):
    ctx, model, cid = _ready(tmp_path, template="INTERVIEW")
    judge = FakeTextModel(model="fake-interview-judge")
    ctx.use_models(model, judge)
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"})
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)

    model.add("AGENT", interview_author)
    if retry:
        judge.add("JUDGE", {"decisions": []})
        with pytest.raises(ValueError, match="judge"):
            run_s8(ctx, cid, [])
        failed_rev = ctx.state(cid).stage("s8").currentRev
        assert ctx.state(cid).stage("s8").status == "CHECK_FAILED"
        judge.requests.clear()
        model.requests.clear()
    judge.add("JUDGE", interview_judge)
    plan = full_plan(ctx, cid)
    folder = run_s8(ctx, cid, [])
    if retry:
        assert folder.name != failed_rev
    result = read_json(folder / "prompt-pair.json")
    evidence = read_json(folder / "evidence-review.json")
    review_artifact = folder / next(iter(evidence["analysisArtifacts"]))
    approved = {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    s8_requests = [r for m in (model, judge) for r in m.requests if r.stage == "s8"]

    # The plan reserves one format repair; valid authored cards never use it.
    assert sum(p.calls for p in plan) == 4 and len(s8_requests) == 3
    assert all(CANARY not in m.content for r in s8_requests for m in r.messages)
    author = next(r for r in s8_requests if r.ref.endswith("/author"))
    records = json.loads(author.messages[-1].content)["records"]
    assert records and all(r["questionType"] == "기타" for r in records)
    assert evidence["sampling"]["version"] == "source-cluster-v2"
    assert set(evidence["sampling"]["authorIds"]) <= set(evidence["sampling"]["questionIds"])
    long_text = result["long"]["text"]
    # New interview packets carry the facts guard and no meta filler for empty sections.
    assert evidence["cards"][-1] == FACTS_GUARD_CARD
    assert "\n[KNOWS_AND_LIMITS]\n" + FACTS_GUARD + "\n" in long_text
    assert NEUTRAL not in long_text and "자료" not in long_text
    assert result["systemRulesRef"] == "builtin:interview-editor-v2"
    assert len(result["sections"]) == 8
    assert evidence["cards"][0]["scope"] == "LOCAL"
    assert read_json(folder / "evidence-packet.json")["facts"] in result["long"]["text"]
    assert not (folder / "example-turns.json").exists()
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    with pytest.raises(ValueError, match="근거|검토"):
        approve_gate(ctx, cid, "G6", {"decision": "APPROVE", "reviewer": "test"})
    raw = review_artifact.read_bytes()
    review_artifact.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="근거|검토|해시|바뀌"):
        approve_gate(ctx, cid, "G6", approved)
    review_artifact.write_bytes(raw)
    approve_gate(ctx, cid, "G6", approved)
    scene = Scene.read(ctx.character_dir(cid))
    assert scene.compose() == result["long"]["text"].rstrip("\n")
    assert [m.role for m in scene.opening()] == ["system"]


REPAIRED_LIMIT = "공적인 판단을 묻는 장면까지 넓히지 않는다."


def _author_with_empty_limit(req):
    if req.ref.endswith("/repair"):
        data = json.loads(req.messages[-1].content)
        assert [c["fix"] for c in data["cards"]] == [
            {"limit": "비어 있다. 반드시 한 문장으로 쓴다"}
        ]
        return {"cards": [dict(id=data["cards"][0]["id"], limit=REPAIRED_LIMIT)]}
    out = interview_author(req)
    if req.ref.endswith("/author"):
        out["cards"][0]["limit"] = ""
    return out


def test_interview_card_with_empty_limit_is_repaired_once_and_reaches_g6(tmp_path):
    ctx, model, cid = _ready(tmp_path, template="INTERVIEW")
    judge = FakeTextModel(model="fake-interview-judge")
    ctx.use_models(model, judge)
    run_s3_twin(ctx, cid)
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "test"})
    model.add("AGENT", lambda req: trait_sheet_for(ctx, cid))
    run_s7(ctx, cid)
    model.add("AGENT", _author_with_empty_limit)
    judge.add("JUDGE", interview_judge)
    folder = run_s8(ctx, cid, [])
    phases = [
        r.ref.rsplit("/", 1)[-1] for m in (model, judge) for r in m.requests if r.stage == "s8"
    ]
    assert sorted(phases) == ["author", "classify", "judge", "repair"]
    evidence = read_json(folder / "evidence-review.json")
    assert evidence["formatRepair"]["cards"] == [
        dict(id="card-01", fields=["limit"], outcome="CANDIDATE_FOR_G6")
    ]
    assert evidence["cards"][0]["limit"] == REPAIRED_LIMIT
    assert REPAIRED_LIMIT in read_json(folder / "prompt-pair.json")["long"]["text"]
    approved = {"decision": "APPROVE", "reviewer": "test", "evidenceReviewed": True}
    approve_gate(ctx, cid, "G6", approved)
    verify_review(ctx, cid, folder, approved=True)
