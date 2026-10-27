"""배경 → 장면·자세 → 합성의 사람 관문을 가짜 공급자로 검증한다. 네트워크 없음."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from character_factory_poc.cli import main
from character_factory_poc.common.errors import (
    BudgetExceeded,
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
)
from character_factory_poc.common.schema import validate
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.providers.fake_image import FakeImageModel, solid_png
from character_factory_poc.stages.s4_frames.approve import load_approved_frames
from character_factory_poc.stages.s4_frames.run import plan_calls as frame_calls
from character_factory_poc.stages.s4_frames.run import run_s4
from character_factory_poc.stages.s4a_backgrounds.approve import load_background_selection
from character_factory_poc.stages.s4a_backgrounds.run import codex_checks as scout_checks
from character_factory_poc.stages.s4a_backgrounds.run import plan_calls as background_calls
from character_factory_poc.stages.s4a_backgrounds.run import run_s4a
from character_factory_poc.stages.s4b_poses.approve import load_scene_and_pose
from character_factory_poc.stages.s4b_poses.run import codex_checks as scene_checks
from character_factory_poc.stages.s4b_poses.run import plan_calls as pose_calls
from character_factory_poc.stages.s4b_poses.run import run_s4b
from tests.support.flow import approve_plan_v2, make_ctx, through_s2
from tests.test_agentic import BRIEF

CH = ("ch1", "ch2", "ch3")


def read(path):
    return json.loads(path.read_text("utf-8"))


def agent_input(req, name):
    text = req.messages[1].content
    found = re.search(rf'<input name="{name}">\n(.*?)\n</input>', text, re.S)
    assert found, name
    return json.loads(found[1])


def backgrounds(req=None):
    return {
        "chapters": [
            {
                "chapterId": ch,
                "candidates": [
                    {
                        "candidateId": f"{ch}-b{i}",
                        "place": f"{ch} 동네 공간 {i}",
                        "timeOfDay": "해 질 무렵",
                        "why": "필름 사진을 찍으며 걷는 동선이다",
                        "props": ["벤치"],
                        "mood": "따뜻한 빛",
                        "sceneFactsDraft": ["벤치가 있다", "창가에 빛이 든다"],
                        "boundariesDraft": ["실제 상호를 말하지 않는다"],
                        "plateBrief": f"Empty Korean courtyard {ch} {i}, no people, no person.",
                    }
                    for i in range(1, 4)
                ],
            }
            for ch in CH
        ]
    }


def scenes(req):
    chosen = agent_input(req, "chosen-backgrounds")
    return {
        "chapters": [
            {
                "chapterId": b["chapterId"],
                "source": b["source"],
                "candidateId": b.get("candidateId"),
                "place": b.get("candidate", {}).get("place", "강변의 작은 산책 쉼터"),
                "timeOfDay": "해 질 무렵",
                "props": ["벤치"],
                "mood": "따뜻한 빛",
                "sceneFacts": ["두 사람 곁에 빈 벤치가 있다", "길을 따라 가로등이 켜졌다"],
                "meetingContext": "미리 정한 약속 장소에서 만났다",
                "relationshipCanon": []
                if b["chapterId"] == "ch1"
                else ["앞선 만남에서 다음 약속을 했다"],
                "sceneBoundaries": ["아직 연인이라고 부르지 않는다"],
                "plateBrief": "Empty riverside walkway, no people, warm evening light.",
            }
            for b in chosen
        ]
    }


def poses(req=None):
    return {
        "chapters": [
            {
                "chapterId": ch,
                "candidates": [
                    {
                        "poseId": f"{ch}-p{i}",
                        "title": f"자세 {i}",
                        "body": "벤치에 앉아 상체를 살짝 돌린다",
                        "hands": "두 손을 무릎에 편안하게 둔다",
                        "props": "가방은 옆에 둔다",
                        "gaze": "상대를 본다",
                        "expression": "작게 웃는다",
                        "shot": "허리 위 중간 샷",
                        "outfit": f"{ch}의 연한 면 셔츠와 긴 바지",
                        "motionHint": "고개를 살짝 끄덕인다",
                        "animatable": True,
                    }
                    for i in range(1, 4)
                ],
            }
            for ch in CH
        ]
    }


@pytest.fixture
def flow(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)
    cid = through_s2(ctx)
    approve_plan_v2(ctx, cid)
    image = FakeImageModel()
    ctx.use_image(image)
    return ctx, agents, cid, image


def choose_bg(ctx, cid, custom=False):
    out = run_s4a(ctx, cid)
    answer = {"decision": "APPROVE", "reviewer": "u"}
    if custom:
        answer = {
            "decision": "SELECT",
            "picks": {"ch1": "ch1-b2", "ch2": "ch2-b1"},
            "custom": {"ch3": "강변 산책길 끝의 조용한 쉼터. 노을이 보인다."},
            "reviewer": "u",
        }
    approve_gate(ctx, cid, "G4a", answer)
    return out


def through_pose(ctx, cid):
    choose_bg(ctx, cid)
    out = run_s4b(ctx, cid)
    approve_gate(ctx, cid, "G4b", {"decision": "APPROVE", "reviewer": "u"})
    return out


def assert_vertical(path):
    raw = path.read_bytes()
    w, h = int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")
    assert abs(w / h - 9 / 16) < 0.02


def test_offline_flow_and_partial_regeneration(flow):
    ctx, agents, cid, image = flow
    bg = choose_bg(ctx, cid, custom=True)
    assert bg.name == "bg1" and len(image.requests) == 9
    assert all(r.stage == "s4a" and r.size == "1024x1536" for r in image.requests)
    for plate in (bg / "plates").glob("*.png"):
        assert_vertical(plate)
    assert len(list((bg / "plates").glob("*.png"))) == 9
    assert 'value="ch1-b2"' in (bg / "gate-G4a.html").read_text("utf-8")
    assert 'id="custom-ch3"' in (bg / "gate-G4a.html").read_text("utf-8")
    bset, selection, _ = load_background_selection(ctx, cid)
    assert bset.backgroundRev == "bg1" and "ch3" in selection.custom

    def retry_pose(req):
        out = poses()
        if agents.calls.count("s4b-pose") == 1:
            out["chapters"][0]["candidates"][0]["hands"] = "rest hand on chin"
        return out

    agents.set("s4b-pose", retry_pose)
    ps = run_s4b(ctx, cid)
    assert ps.name == "ps1" and agents.calls.count("s4b-pose") == 2
    assert len(image.requests) == 10 and image.requests[-1].stage == "s4b"
    scene = read(ps / "scene-plan.json")
    for ch, chosen in (("ch1", "ch1-b2"), ("ch2", "ch2-b1")):
        s = next(s for s in scene["chapters"] if s["chapterId"] == ch)
        assert (ps / s["plate"]["path"]).read_bytes() == (
            bg / "plates" / f"{chosen}.png"
        ).read_bytes()
        assert s["place"] == f"{ch} 동네 공간 {chosen[-1]}" and s["source"] == "CANDIDATE"
    assert scene["chapters"][2]["source"] == "USER"
    assert scene["chapters"][1]["relationshipCanon"]
    for chapter in scene["chapters"]:
        assert_vertical(ps / chapter["plate"]["path"])
    page = (ps / "gate-G4b.html").read_text("utf-8")
    assert "sceneFacts" in page and "relationshipCanon" in page and 'id="ch1-hands"' in page
    approve_gate(
        ctx,
        cid,
        "G4b",
        {
            "decision": "SELECT",
            "picks": {"ch1": "ch1-p2", "ch2": "ch2-p3"},
            "custom": {"ch3": "난간 옆에 서서 두 손은 허리 아래에 모은다. 남색 재킷을 입는다."},
            "tweaks": {"ch1": {"hands": "두 손으로 닫힌 책을 무릎 위에 잡는다"}},
            "reviewer": "u",
        },
    )
    scene_model, pose, _ = load_scene_and_pose(ctx, cid)
    assert pose.chapters[0].tweaked == ["hands"] and "닫힌 책" in pose.chapters[0].hands
    assert pose.chapters[2].source == "USER" and pose.chapters[2].customText
    image.requests.clear()
    fr1 = run_s4(ctx, cid)
    assert len(image.requests) == 3
    assert ctx.state(cid).stage("s4").status == "AWAITING_HUMAN"
    for req, ch in zip(image.requests, scene_model.chapters, strict=True):
        assert req.reference_images[0] == str(fr1 / "reference" / "c2-1.png")
        assert Path(req.reference_images[1]).read_bytes() == (ps / ch.plate.path).read_bytes()
        assert len(req.reference_images) == 2 and "9:16" in req.prompt
        assert ch.place in req.prompt and "identity" in req.prompt and "not for pose" in req.prompt
        assert (
            "do not rest the chin" in req.prompt and "chin resting on hand" in req.negative_prompt
        )
        assert_vertical(fr1 / ch.chapterId / "f1.png")
    inputs = read(fr1 / "inputs.json")
    assert inputs["schemaVersion"] == "frames-inputs-v2" and inputs["referenceCrop"] == "full"
    assert "찾지 못해" in inputs["cropNote"]
    assert "reference/c2-1.png" in (fr1 / "gate-G4.html").read_text("utf-8")
    approve_gate(
        ctx,
        cid,
        "G4",
        {
            "decision": "REQUEST_CHANGES",
            "reviewer": "u",
            "requestedChanges": [{"field": "ch2", "note": "가방을 왼쪽으로 옮긴다"}],
        },
    )
    with pytest.raises(GateNotApprovedError):
        load_approved_frames(ctx, cid)
    image.requests.clear()
    fr2 = run_s4(ctx, cid)
    assert fr2.name == "fr2" and len(image.requests) == 1
    assert "Revision note: 가방을 왼쪽으로 옮긴다" in image.requests[0].prompt
    assert read(fr2 / "inputs.json")["regenerate"] == ["ch2"]
    assert read(fr2 / "inputs.json")["carriedFrom"] == "fr1"
    old, new = read(fr1 / "frames.json"), read(fr2 / "frames.json")
    for i in (0, 2):
        assert (fr1 / CH[i] / "f1.png").read_bytes() == (fr2 / CH[i] / "f1.png").read_bytes()
        # 생성 기록은 유지하고 이월 출처만 추가한다. 이미지 바이트는 위에서 비교한다.
        assert new[i] == old[i] | {
            "settings": old[i]["settings"] | {"carriedFrom": "fr1"},
        }
    assert (fr1 / "ch2/f1.png").read_bytes() != (fr2 / "ch2/f1.png").read_bytes()
    approve_gate(ctx, cid, "G4", {"decision": "APPROVE", "reviewer": "u", "minutes": 4})
    approved, rev_dir = load_approved_frames(ctx, cid)
    assert rev_dir == fr2 and [f.frameId for f in approved.frames] == [f"{ch}-f1" for ch in CH]
    assert any(h["gate"] == "G4" and h["minutes"] == 4 for h in ctx.ledger(cid).human())
    assert main(["--root", str(ctx.config.root), "verify", cid]) == 0


@pytest.mark.parametrize("mode", ["face", "full"])
def test_identity_crop(flow, monkeypatch, mode):
    import character_factory_poc.stages.s4_frames.run as runner

    ctx, _, cid, image = flow
    through_pose(ctx, cid)
    if mode == "face":
        monkeypatch.setattr(
            runner, "crop_face", lambda data, scale: (solid_png(30, 30, (1, 2, 3)), (1, 2, 30, 30))
        )
    else:
        ctx.config.stages["s4"] = {"reference_crop": "full"}
        monkeypatch.setattr(runner, "crop_face", lambda *a, **k: pytest.fail("크롭하면 안 된다"))
    image.requests.clear()
    out = run_s4(ctx, cid)
    inputs = read(out / "inputs.json")
    assert inputs["referenceCrop"] == mode
    fname = "c2-1-face.png" if mode == "face" else "c2-1.png"
    assert all(r.reference_images[0] == str(out / "reference" / fname) for r in image.requests)
    assert f"reference/{fname}" in (out / "gate-G4.html").read_text("utf-8")
    assert main(["--root", str(ctx.config.root), "verify", cid]) == 0


def test_v1_plan_is_rejected(tmp_path):
    from character_factory_poc.stages.s3_plan.draft import run_s3_draft
    from tests.test_frames import agent

    ctx, _ = make_ctx(tmp_path)
    ctx._text.add("AGENT", agent)
    cid = through_s2(ctx)
    run_s3_draft(ctx, cid, BRIEF)
    approve_gate(ctx, cid, "G3", {"decision": "APPROVE", "reviewer": "u"})
    with pytest.raises(CheckFailed, match="character-plan-v2"):
        run_s4a(ctx, cid)


@pytest.mark.parametrize("gate", ["G4a", "G4b"])
@pytest.mark.parametrize(
    "change",
    [
        {"picks": {"ch1": "ch2-b1", "ch2": "ch2-b1", "ch3": "ch3-b1"}},
        {"picks": {"ch1": "ch1-b1"}},
        {"picks": {"ch1": "ch1-b1", "ch2": "ch2-b1", "ch3": "ch3-b1"}, "custom": {"ch1": "겹침"}},
        {"custom": {"ch1": " ", "ch2": "x", "ch3": "x"}},
        {"picks": ["bad"]},
    ],
)
def test_invalid_gate_answers(flow, gate, change):
    ctx, _, cid, _ = flow
    if gate == "G4a":
        run_s4a(ctx, cid)
    else:
        choose_bg(ctx, cid)
        run_s4b(ctx, cid)
        change = json.loads(json.dumps(change).replace("-b", "-p"))
    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, gate, {"decision": "SELECT", "reviewer": "u", **change})
    assert ctx.state(cid).gate(gate).status == "AWAITING_HUMAN"


@pytest.mark.parametrize(
    "tweaks", [{"ch4": {"hands": "x"}}, {"ch1": {"bad": "x"}}, {"ch1": {"hands": "턱을 괸다"}}]
)
def test_invalid_pose_tweaks(flow, tweaks):
    ctx, _, cid, _ = flow
    choose_bg(ctx, cid)
    run_s4b(ctx, cid)
    with pytest.raises(FactoryError):
        approve_gate(
            ctx,
            cid,
            "G4b",
            {
                "decision": "SELECT",
                "reviewer": "u",
                "picks": {c: f"{c}-p1" for c in CH},
                "tweaks": tweaks,
            },
        )


@pytest.mark.parametrize(
    "answer",
    [
        {"decision": "SELECT", "selections": ["ch1-f1", "ch2-f1"]},
        {"decision": "SELECT", "selections": ["ch1-f1", "ch1-f1", "ch2-f1", "ch3-f1"]},
        {"decision": "SELECT", "selections": ["ch1-f1", "ch2-f1", "ch3-f9"]},
        {"decision": "REQUEST_CHANGES", "requestedChanges": []},
        {"decision": "REQUEST_CHANGES", "requestedChanges": [{"field": "ch4", "note": "x"}]},
        {"decision": "REQUEST_CHANGES", "requestedChanges": [{"field": "ch2", "note": " "}]},
    ],
)
def test_invalid_g4(flow, answer):
    ctx, _, cid, _ = flow
    through_pose(ctx, cid)
    run_s4(ctx, cid)
    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, "G4", {"reviewer": "u", **answer})
    assert ctx.state(cid).gate("G4").status == "AWAITING_HUMAN"


def test_dry_run_and_budget_before_writes(flow):
    ctx, _, cid, image = flow
    # 이미지 최대 (1 + 수정 2회) × 장수, 판정은 형식 재질의까지 그 두 배
    assert sum(p.calls for p in background_calls(ctx)) == 82
    assert sum(p.calls for p in pose_calls(ctx)) == 29
    assert sum(p.calls for p in frame_calls(ctx)) == 27
    ctx.max_calls = 0
    with pytest.raises(BudgetExceeded):
        run_s4a(ctx, cid)
    assert not (ctx.character_dir(cid) / "s4a-backgrounds").exists() and not image.requests


def test_dependencies(tmp_path):
    from character_factory_poc.stages.s3_plan.draft import new_character

    ctx, _ = make_ctx(tmp_path)
    cid = new_character(ctx, "deps")
    for run, gate in [(run_s4a, "G3"), (run_s4b, "G4a"), (run_s4, "G4b")]:
        with pytest.raises(GateNotApprovedError, match=gate):
            run(ctx, cid)


def test_codex_checks_match_runner(flow):
    ctx, _, cid, _ = flow
    bg = choose_bg(ctx, cid)
    ps = run_s4b(ctx, cid)
    for stage, workspace, checks in [
        ("s4a", bg / "workspace", scout_checks),
        ("s4b-scene", ps / "workspace-scene", scene_checks),
        ("s4b-pose", ps / "workspace-pose", scene_checks),
    ]:
        contract, functions = checks(stage, workspace)
        obj = validate(contract, read(workspace / "output.json"))
        assert [p for fn in functions for p in fn(obj)] == []


def test_bad_scene_and_background_fail_before_images(flow):
    ctx, agents, cid, image = flow
    bad = backgrounds()
    bad["chapters"][0]["candidates"][0]["plateBrief"] = "a woman in a courtyard"
    agents.set("s4a", lambda req: bad)
    with pytest.raises(CheckFailed):
        run_s4a(ctx, cid)
    assert not image.requests and ctx.state(cid).stage("s4a").status == "CHECK_FAILED"
    agents.set("s4a", backgrounds)
    choose_bg(ctx, cid)

    def wrong_place(req):
        out = scenes(req)
        out["chapters"][0]["place"] = "다른 장소"
        return out

    agents.set("s4b-scene", wrong_place)
    image.requests.clear()
    with pytest.raises(CheckFailed):
        run_s4b(ctx, cid)
    assert not image.requests and ctx.state(cid).stage("s4b").status == "CHECK_FAILED"


def test_ratio_drift_marks_failure(flow):
    ctx, _, cid, _ = flow

    class Square(FakeImageModel):
        def generate(self, request):
            return super().generate(replace(request, size="1024x1024"))

    ctx.use_image(Square())
    with pytest.raises(CheckFailed, match="비율"):
        run_s4a(ctx, cid)
    assert ctx.state(cid).stage("s4a").status == "CHECK_FAILED"


def test_orchestrator_waits_at_each_scene_gate(flow):
    from character_factory_poc.pipeline.orchestrator import RunOptions, run_until

    ctx, _, cid, _ = flow
    for gate in ("G4a", "G4b", "G4"):
        log = run_until(ctx, cid, RunOptions(until=gate))
        assert log.stopped_at == gate and ctx.state(cid).gate(gate).status == "AWAITING_HUMAN"
        if gate != "G4":
            approve_gate(ctx, cid, gate, {"decision": "APPROVE", "reviewer": "u"})
    assert ctx.state(cid).stage("s7").status == "PENDING"


def test_cli_dry_run_has_no_side_effects(flow, capsys):
    ctx, _, cid, image = flow
    assert main(["--root", str(ctx.config.root), "frames", "run", cid]) == 0
    output = capsys.readouterr().out
    assert "아직 실행할 수 없다" in output
    assert "합계 27회" in output and "9:16" in output
    assert not image.requests and not (ctx.character_dir(cid) / "s4-frames").exists()


def test_later_dependencies_require_approved_gates(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = through_s2(ctx)
    with pytest.raises(GateNotApprovedError, match="G3"):
        run_s4a(ctx, cid)
    with pytest.raises(GateNotApprovedError, match="G4b"):
        run_s4(ctx, cid)


@pytest.mark.parametrize("stage", ["s4b", "s4"])
def test_budget_stops_before_new_revision(flow, stage):
    ctx, _, cid, image = flow
    if stage == "s4b":
        choose_bg(ctx, cid)
        run, folder = run_s4b, "s4b-poses"
    else:
        through_pose(ctx, cid)
        run, folder = run_s4, "s4-frames"
    image.requests.clear()
    ctx.max_calls = 0
    with pytest.raises(BudgetExceeded):
        run(ctx, cid)
    assert not image.requests and not (ctx.character_dir(cid) / folder).exists()


def test_changed_scene_revision_regenerates_every_chapter(flow):
    ctx, _, cid, image = flow
    through_pose(ctx, cid)
    first = run_s4(ctx, cid)
    approve_gate(
        ctx,
        cid,
        "G4",
        {
            "decision": "REQUEST_CHANGES",
            "reviewer": "u",
            "requestedChanges": [{"field": "ch2", "note": "자세를 바꾼다"}],
        },
    )
    run_s4b(ctx, cid)
    approve_gate(ctx, cid, "G4b", {"decision": "APPROVE", "reviewer": "u"})
    image.requests.clear()
    second = run_s4(ctx, cid)
    assert first.name == "fr1" and second.name == "fr2" and len(image.requests) == 3
    assert read(second / "inputs.json")["regenerate"] == list(CH)
    assert read(second / "inputs.json")["carriedFrom"] is None


def test_backgrounds_without_plates_generate_chosen_plates_in_s4b(flow):
    ctx, _, cid, image = flow
    ctx.config.stages["s4a"] = {"plates": False}
    bg = choose_bg(ctx, cid)
    assert not image.requests and not (bg / "plates").exists()
    out = run_s4b(ctx, cid)
    assert len(image.requests) == 3 and all(r.stage == "s4b" for r in image.requests)
    assert all(c["plate"] for c in read(out / "scene-plan.json")["chapters"])


@pytest.mark.parametrize("gate", ["G4a", "G4b"])
@pytest.mark.parametrize("decision", ["REJECT", "REQUEST_CHANGES"])
def test_earlier_gate_rejection_allows_new_revision(flow, gate, decision):
    ctx, _, cid, _ = flow
    if gate == "G4a":
        run, expected = run_s4a, "bg2"
    else:
        choose_bg(ctx, cid)
        run, expected = run_s4b, "ps2"
    run(ctx, cid)
    approve_gate(
        ctx, cid, gate, {"decision": decision, "reviewer": "u", "reasons": "다른 안을 원한다"}
    )
    assert ctx.state(cid).gate(gate).status == "REJECTED"
    assert run(ctx, cid).name == expected


def test_ranking_names_never_reach_image_calls(flow):
    from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking
    from tests.support.synthetic import RANKING

    ctx, agents, cid, image = flow
    name = all_names(load_ranking(RANKING))[0]
    bad = backgrounds()
    bad["chapters"][0]["candidates"][0]["place"] = f"{name}의 공간"
    agents.set("s4a", lambda req: bad)
    with pytest.raises(CheckFailed, match="이름"):
        run_s4a(ctx, cid)
    assert image.requests == []
    inputs = ctx.character_dir(cid) / "s4a-backgrounds/bg1/workspace/inputs"
    assert all(name not in path.read_text("utf-8") for path in inputs.iterdir())


@pytest.mark.parametrize("stage", ["s4a", "s4b-scene", "s4b-pose"])
def test_bad_agent_contract_semantics(stage, flow):
    from character_factory_poc.stages.s4a_backgrounds.run import check_backgrounds
    from character_factory_poc.stages.s4b_poses.run import check_poses, check_scenes

    if stage == "s4a":
        out = backgrounds()
        out["chapters"][0]["candidates"][1]["place"] = out["chapters"][0]["candidates"][0]["place"]
        out["chapters"][1]["candidates"][0]["candidateId"] = "ch1-b1"
        functions = [check_backgrounds(3, [])]
        obj = validate("background-candidates-output-v1", out)
        assert len(functions[0](obj)) >= 2
    elif stage == "s4b-pose":
        out = poses()
        out["chapters"][0]["candidates"][0]["animatable"] = False
        out["chapters"][1]["candidates"][0]["outfit"] = " "
        obj = validate("pose-candidates-output-v1", out)
        assert len(check_poses(3, [])(obj)) == 2
    else:
        ctx, _, cid, _ = flow
        choose_bg(ctx, cid)
        out_dir = run_s4b(ctx, cid)
        chosen = read(out_dir / "workspace-scene/inputs/chosen-backgrounds.json")
        raw = read(out_dir / "workspace-scene/output.json")
        raw["chapters"][1]["relationshipCanon"] = []
        raw["chapters"][2]["source"] = "USER"
        obj = validate("scene-writer-output-v1", raw)
        assert len(check_scenes(chosen, [])(obj)) == 2
