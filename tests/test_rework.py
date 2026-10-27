"""수정 요청 재작업 (LLD §6.9, 명세 §7.3, FR-46, D-0049). 네트워크 없음.

사람 메모 → `rework-brief-v1` → 요청한 부분만 새 revision으로 다시 만들고 같은 관문을 다시 연다.
- G4a·G4b: 대상 챕터만 새로 만들고 다른 챕터의 후보·배경 사진은 바이트 그대로 이월한다.
- G5: 영상 후보 전체를 다시 만들되 메모를 움직임 지시에 붙인다.
- G6: 프롬프트 쌍을 다시 만들고 s9s는 새 G6 승인 전까지 시작하지 않는다.
- G1: --ranking이 없어도 같은 근거로 얼굴만 다시 만든다(`cfp ref faces` 경로).
- 반복 상한: `[rework] max_rounds`를 넘으면 사람 허락(`RunOptions.confirmed`) 전에는 안 돈다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import validate
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.pipeline.rework import (
    REWORK_GATES,
    prepare_rework,
    rework_rounds,
    rework_status,
)
from character_factory_poc.stages.s3_plan.draft import new_character
from character_factory_poc.stages.s5_intro.run import run_s5
from character_factory_poc.web import reads
from tests.support.flow import approve_plan_v2, make_ctx, through_s2
from tests.support.synthetic import RANKING, prompter_output
from tests.support.web_gates import trait_sheet_for
from tests.test_scene_flow import backgrounds, poses, scenes

CH = ("ch1", "ch2", "ch3")


def agent_input(req, name):
    text = req.messages[1].content
    found = re.search(rf'<input name="{name}">\n(.*?)\n</input>', text, re.S)
    return json.loads(found[1]) if found else None


def latest(char_dir: Path, folder: str, prefix: str) -> str:
    names = [p.name for p in (char_dir / folder).glob(f"{prefix}*") if p.is_dir()]
    return max(names, key=lambda n: int(n[len(prefix) :]))


def brief_at(char_dir: Path, gate: str, rev: str):
    """관문 revision에 묶인 브리프 파일. 실행이 끝나면 gate.rev가 바뀌어 load_rework는 None이다."""
    return validate("rework-brief-v1", read_json(char_dir / "rework" / f"{gate}-{rev}.json"))


def revised_backgrounds(req):
    """수정 대상 챕터만 다른 장소·plateBrief로 답하는 Location Scout."""
    out = backgrounds()
    revision = agent_input(req, "revision")
    for ch in (revision or {}).get("targets", []):
        chapter = next((c for c in out["chapters"] if c["chapterId"] == ch), None)
        if chapter is None:
            continue
        for i, candidate in enumerate(chapter["candidates"], 1):
            candidate["place"] = f"{ch} 고친 장소 {i}"
            candidate["plateBrief"] = f"Empty revised courtyard {ch} {i}, no people."
    return out


def revised_scenes(req):
    out = scenes(req)
    for ch in (agent_input(req, "revision") or {}).get("targets", []):
        chapter = next((c for c in out["chapters"] if c["chapterId"] == ch), None)
        if chapter is not None:
            chapter["meetingContext"] = f"{ch} 약속 장소를 바꿨다"
    return out


def revised_poses(req):
    out = poses()
    for ch in (agent_input(req, "revision") or {}).get("targets", []):
        chapter = next((c for c in out["chapters"] if c["chapterId"] == ch), None)
        if chapter is not None:
            for i, candidate in enumerate(chapter["candidates"], 1):
                candidate["body"] = f"{ch} 고친 자세 {i}"
    return out


def to_g4a(tmp_path: Path, extra_toml: str = ""):
    ctx, agents = make_ctx(tmp_path, extra_toml)
    requests: list = []

    def scout(req):
        requests.append(req)
        return revised_backgrounds(req)

    agents.set("s4a", scout)
    agents.set("s4b-scene", revised_scenes)
    agents.set("s4b-pose", revised_poses)
    cid = through_s2(ctx)
    approve_plan_v2(ctx, cid)
    log = run_until(ctx, cid, RunOptions(until="G4a"))
    assert log.waiting == ["G5", "G4a"]
    assert ctx.state(cid).gate("G4a").status == "AWAITING_HUMAN"
    return ctx, agents, cid, requests


def request_changes(ctx, cid, gate, changes, reasons=""):
    answer = {"decision": "REQUEST_CHANGES", "reviewer": "u", "requestedChanges": changes}
    if reasons:
        answer["reasons"] = reasons
    approve_gate(ctx, cid, gate, answer)


def test_g4a_partial_rework_keeps_other_chapters(tmp_path):
    ctx, _agents, cid, requests = to_g4a(tmp_path)
    char_dir = ctx.character_dir(cid)
    first = char_dir / "s4a-backgrounds" / "bg1"
    note = "창가 자리를 옆자리로 바꾼다"
    request_changes(ctx, cid, "G4a", [{"field": "ch2", "note": note}])

    log = run_until(ctx, cid, RunOptions(until="G4a"))
    assert log.steps and ctx.state(cid).gate("G4a").status == "AWAITING_HUMAN"
    second = char_dir / "s4a-backgrounds" / "bg2"
    assert second.is_dir()

    old = read_json(first / "background-candidates.json")
    new = read_json(second / "background-candidates.json")
    assert new["backgroundRev"] == "bg2"
    by_ch = {c["chapterId"]: c for c in old["chapters"]}
    new_by_ch = {c["chapterId"]: c for c in new["chapters"]}
    for ch in ("ch1", "ch3"):
        assert new_by_ch[ch] == by_ch[ch]
        for candidate in by_ch[ch]["candidates"]:
            plate = candidate["plate"]
            assert sha256_file(first / plate["path"]) == plate["sha256"]
            assert (second / plate["path"]).read_bytes() == (first / plate["path"]).read_bytes()
    assert new_by_ch["ch2"] != by_ch["ch2"]
    assert "고친 장소" in new_by_ch["ch2"]["candidates"][0]["place"]
    page = (second / "gate-G4a.html").read_text("utf-8")
    assert 'id="change-ch2"' in page and "requestedChanges" in page

    # 사람 메모 원문이 단계 에이전트 입력과 브리프에 그대로 남는다(FR-46).
    assert note in requests[-1].messages[1].content
    brief = brief_at(char_dir, "G4a", "bg1")
    assert brief is not None and brief.fromRev == "bg1" and brief.round == 1
    assert [t.field for t in brief.targets] == ["ch2"] and brief.targets[0].note == note
    assert brief.keep == ["ch1", "ch3"] and brief.normalizedBy is None
    assert brief.instructions == note
    assert (char_dir / "rework" / "G4a-bg1.json").exists()

    view = reads.gate_view(ctx.config.root, cid, "G4a")
    assert view["rework"] == {"round": 1, "maxRounds": 3, "capReached": False}
    assert reads.gate_view(ctx.config.root, cid, "G3")["rework"] is None


def test_g4b_partial_rework_keeps_other_chapters(tmp_path):
    ctx, _agents, cid, _requests = to_g4a(tmp_path)
    char_dir = ctx.character_dir(cid)
    approve_gate(ctx, cid, "G4a", {"decision": "APPROVE", "reviewer": "u"})
    log = run_until(ctx, cid, RunOptions(until="G4b"))
    assert ctx.state(cid).gate("G4b").status == "AWAITING_HUMAN", log.steps
    first = char_dir / "s4b-poses" / "ps1"
    assert (first / "pose-candidates.json").exists()
    request_changes(ctx, cid, "G4b", [{"field": "ch2", "note": "손 위치를 무릎으로"}])

    run_until(ctx, cid, RunOptions(until="G4b"))
    second = char_dir / "s4b-poses" / "ps2"
    assert second.is_dir()
    old_scene = {c["chapterId"]: c for c in read_json(first / "scene-plan.json")["chapters"]}
    new_scene = {c["chapterId"]: c for c in read_json(second / "scene-plan.json")["chapters"]}
    for ch in ("ch1", "ch3"):
        assert new_scene[ch] == old_scene[ch]
        plate = old_scene[ch]["plate"]
        assert (second / plate["path"]).read_bytes() == (first / plate["path"]).read_bytes()
    assert new_scene["ch2"] != old_scene["ch2"]
    old_pose = {c["chapterId"]: c for c in read_json(first / "pose-candidates.json")["chapters"]}
    new_pose = {c["chapterId"]: c for c in read_json(second / "pose-candidates.json")["chapters"]}
    assert new_pose["ch1"] == old_pose["ch1"] and new_pose["ch3"] == old_pose["ch3"]
    assert new_pose["ch2"] != old_pose["ch2"]
    brief = brief_at(char_dir, "G4b", "ps1")
    assert brief is not None and brief.fromRev == "ps1" and brief.keep == ["ch1", "ch3"]


def test_rework_round_cap_and_confirmed_allowance(tmp_path):
    ctx, agents, cid, _requests = to_g4a(tmp_path)
    # s4a가 막혀도 다른 갈래(s7 → s8)는 계속 돈다(D-0035). 그 갈래의 가짜 응답을 준비한다.
    agents.set("s7", lambda req: trait_sheet_for(ctx, cid))
    agents.set("s8", lambda req: prompter_output())
    char_dir = ctx.character_dir(cid)
    for expected in ("bg2", "bg3", "bg4"):
        request_changes(ctx, cid, "G4a", [{"field": "ch2", "note": "조금 더 밝게"}])
        run_until(ctx, cid, RunOptions(until="G4a"))
        assert latest(char_dir, "s4a-backgrounds", "bg") == expected
        assert rework_rounds(char_dir, "G4a") == int(expected[-1]) - 1

    request_changes(ctx, cid, "G4a", [{"field": "ch2", "note": "네 번째 요청"}])
    log = run_until(ctx, cid, RunOptions(until="G4a"))
    assert "s4a" in log.blocked
    assert any("반복 상한" in step for step in log.steps)
    assert latest(char_dir, "s4a-backgrounds", "bg") == "bg4"
    assert ctx.state(cid).gate("G4a").status == "REJECTED"
    status = rework_status(char_dir, "G4a", {"max_rounds": 3})
    assert status == {"round": 4, "maxRounds": 3, "capReached": True}

    # 사람이 한 번 더 허락하면 그때는 돈다(opt.confirmed).
    run_until(ctx, cid, RunOptions(until="G4a", confirmed={"s4a"}))
    assert latest(char_dir, "s4a-backgrounds", "bg") == "bg5"
    assert brief_at(char_dir, "G4a", "bg4").round == 4


def test_g6_rework_reopens_gate_and_holds_s9s(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    holder: dict = {}
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)
    agents.set("s7", lambda req: trait_sheet_for(ctx, holder["cid"]))
    requests: list = []

    def prompter(req):
        requests.append(req)
        return prompter_output()

    agents.set("s8", prompter)
    cid = through_s2(ctx)
    holder["cid"] = cid
    approve_plan_v2(ctx, cid)
    log = run_until(
        ctx,
        cid,
        RunOptions(until="G6", auto_approve={"G4a", "G4b", "G4", "G5b"}),
    )
    assert log.waiting == ["G5", "G6"] and ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    char_dir = ctx.character_dir(cid)
    first = ctx.state(cid).gate("G6").rev
    note = "말투가 너무 차갑다"
    request_changes(ctx, cid, "G6", [{"field": "longPrompt", "note": note}])

    log = run_until(ctx, cid, RunOptions(until="s9s"))
    second = ctx.state(cid).gate("G6").rev
    assert second and second != first and (char_dir / "s8-prompts" / second).is_dir()
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    assert ctx.state(cid).stage("s9s").status == "PENDING"
    assert "s9s" in log.blocked
    assert note in requests[-1].messages[1].content
    brief = brief_at(char_dir, "G6", first)
    assert brief is not None and brief.fromRev == first and brief.targets[0].note == note


def test_reject_makes_no_brief_and_rebuilds_all(tmp_path):
    ctx, _agents, cid, _requests = to_g4a(tmp_path)
    char_dir = ctx.character_dir(cid)
    approve_gate(
        ctx, cid, "G4a", {"decision": "REJECT", "reviewer": "u", "reasons": "다른 안을 원한다"}
    )
    assert ctx.state(cid).gate("G4a").status == "REJECTED"
    run_until(ctx, cid, RunOptions(until="G4a"))
    assert latest(char_dir, "s4a-backgrounds", "bg") == "bg2"
    assert not list((char_dir / "rework").glob("G4a-*")) if (char_dir / "rework").is_dir() else True
    assert rework_rounds(char_dir, "G4a") == 0
    new = read_json(char_dir / "s4a-backgrounds" / "bg2" / "background-candidates.json")
    assert len(new["chapters"]) == 3


def test_g1_request_changes_runs_faces_without_ranking(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    cid = new_character(ctx, "g1")
    log = run_until(ctx, cid, RunOptions(until="G1", ranking=RANKING))
    assert log.waiting == ["G1"] and ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"
    calls = agents.calls.count("s1")
    approve_gate(
        ctx,
        cid,
        "G1",
        {"decision": "REQUEST_CHANGES", "reviewer": "u", "note": "눈매를 조금 부드럽게"},
    )
    image = ctx._image
    image.requests.clear()

    run_until(ctx, cid, RunOptions(until="G1"))
    char_dir = ctx.character_dir(cid)
    assert latest(char_dir, "s1-reference", "rf") == "rf2"
    assert agents.calls.count("s1") == calls  # Scout를 다시 부르지 않는다
    assert image.requests and all(r.stage == "s1" for r in image.requests)
    carried = read_json(char_dir / "s1-reference" / "rf2" / "carried-from.json")
    assert carried["fromRev"] == "rf1"
    for name in ("ranking.json", "people.json", "features.json", "report.json"):
        assert (char_dir / "s1-reference" / "rf2" / name).read_bytes() == (
            char_dir / "s1-reference" / "rf1" / name
        ).read_bytes()
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"


def test_g5_rework_puts_memo_into_motion_prompt(tmp_path):
    ctx, _agents = make_ctx(tmp_path)
    cid = through_s2(ctx)
    run_s5(ctx, cid)
    approve_gate(
        ctx,
        cid,
        "G5",
        {"decision": "REQUEST_CHANGES", "reviewer": "u", "reasons": "얼굴이 흔들린다"},
    )
    run_until(ctx, cid, RunOptions(until="G5"))
    char_dir = ctx.character_dir(cid)
    second = latest(char_dir, "s5-intro", "vi")
    assert second == "vi2"
    prompt = read_json(char_dir / "s5-intro" / second / "inputs.json")["settings"]["prompt"]
    assert "얼굴이 흔들린다" in prompt and "Gentle, natural motion" in prompt
    brief = brief_at(char_dir, "G5", "vi1")
    assert brief is not None and brief.fromRev == "vi1"
    assert brief.targets[0].note == "얼굴이 흔들린다"


@pytest.mark.parametrize("normalize", [True, False])
def test_normalize_switch(tmp_path, normalize):
    extra = "[rework]\n" + f"normalize = {str(normalize).lower()}\n"
    ctx, agents, cid, _requests = to_g4a(tmp_path, extra)
    note = "창가 자리를 옆자리로 바꾼다"
    if normalize:
        ctx._text.add("REWORK", lambda req: "수정 지시: 창가 자리를 옆자리로 옮긴다")
    request_changes(ctx, cid, "G4a", [{"field": "ch2", "note": note}])
    run_until(ctx, cid, RunOptions(until="G4a"))
    brief = brief_at(ctx.character_dir(cid), "G4a", "bg1")
    assert brief is not None and brief.targets[0].note == note
    if normalize:
        assert brief.instructions == "수정 지시: 창가 자리를 옆자리로 옮긴다"
        assert brief.normalizedBy is not None and brief.normalizedBy.provider == "fake"
    else:
        assert brief.instructions == note and brief.normalizedBy is None


def test_prepare_rework_ignores_gates_outside_rework(tmp_path):
    ctx, _agents, cid, _requests = to_g4a(tmp_path)
    # G3는 화면에서 칸을 직접 고치므로 재작업 대상이 아니다.
    assert "G3" not in REWORK_GATES
    assert prepare_rework(ctx, cid, "s3", RunOptions(until="G4a")) is True
    assert not list((ctx.character_dir(cid) / "rework").glob("G3-*"))
