"""S4b Scene Writer → 확정 plate → Pose Director. G4b에서 사람이 자세를 고른다."""

from __future__ import annotations

import re
from pathlib import Path

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.qa import QaSummary
from character_factory_poc.contracts.rework import ReworkBrief
from character_factory_poc.contracts.scene import PoseOutput, SceneWriterOutput
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.rework import load_rework
from character_factory_poc.stages.image_qa import ensure_judge, qa_settings, worst_case_calls
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s3_plan.importer import load_approved_plan_v2
from character_factory_poc.stages.s4a_backgrounds.approve import load_background_selection
from character_factory_poc.stages.s4a_backgrounds.run import (
    assert_no_names,
    call_agent,
    carry_qa,
    check_no_names,
    config_for,
    empty_scene_problems,
    make_plate,
    plan_summary,
    ranking_guard,
)
from character_factory_poc.stages.s4b_poses.page import render_g4b_page

DEFAULTS = {"candidates_per_chapter": 3}
CHAPTERS = ("ch1", "ch2", "ch3")
FACE_CONTACT = re.compile(r"턱|볼|얼굴에|얼굴을|입가|chin|cheek|face|mouth", re.I)


def s4b_config(ctx: Context) -> dict:
    return config_for(ctx, "s4b", DEFAULTS)


def plan_calls(ctx: Context, chapter_count: int = 3) -> list[CallPlan]:
    s4b_config(ctx)
    images, judges = worst_case_calls(qa_settings(ctx), chapter_count)
    description = f"직접 정의한 배경 plate 최대 {chapter_count}장"
    if judges:
        description += f" (자동 검사 포함 최대 {images}장)"
    plans = [
        CallPlan("s4b-scene", "Scene Writer 장면 사실과 관계 연속성 작성", 1),
        CallPlan("s4b-pose", "Pose Director 자세·의상 후보 작성", 1),
        CallPlan("s4b", description, images),
    ]
    if judges:
        plans.append(CallPlan("s4b", "배경 plate 비전 자동 검사 (최대)", judges))
    return plans


def hands_problems(text: str) -> list[str]:
    return ["hands에 얼굴 접촉 단어를 쓰지 않는다(D-0027)"] if FACE_CONTACT.search(text) else []


def check_scenes(chosen: list[dict], guard: list[dict]):
    by_chapter = {ch["chapterId"]: ch for ch in chosen}

    def check(out: SceneWriterOutput) -> list[str]:
        problems = check_no_names(out, guard)
        if {ch.chapterId for ch in out.chapters} != set(by_chapter):
            return ["요청한 챕터를 확인한다"]
        for chapter in out.chapters:
            src = by_chapter[chapter.chapterId]
            if src["source"] == "CANDIDATE":
                if (
                    chapter.source != "CANDIDATE"
                    or chapter.candidateId != src["candidateId"]
                    or chapter.place != src["candidate"]["place"]
                ):
                    problems.append(
                        f"{chapter.chapterId}: 선택한 place·source·candidateId를 유지한다"
                    )
            elif (
                chapter.source != "USER"
                or chapter.candidateId is not None
                or not chapter.place.strip()
            ):
                problems.append(f"{chapter.chapterId}: 직접 정의는 source USER, place가 필요하다")
            if chapter.chapterId != "ch1" and not any(t.strip() for t in chapter.relationshipCanon):
                problems.append(f"{chapter.chapterId}: 앞선 챕터의 relationshipCanon이 필요하다")
            if not any(t.strip() for t in chapter.sceneBoundaries):
                problems.append(f"{chapter.chapterId}: sceneBoundaries를 하나 이상 쓴다")
            problems.extend(empty_scene_problems(chapter.plateBrief))
        return problems

    return check


def check_poses(count: int, guard: list[dict], chapters=CHAPTERS):
    def check(out: PoseOutput) -> list[str]:
        problems = check_no_names(out, guard)
        if {ch.chapterId for ch in out.chapters} != set(chapters):
            return ["요청한 챕터를 확인한다"]
        for chapter in out.chapters:
            expected = {f"{chapter.chapterId}-p{i}" for i in range(1, count + 1)}
            if (
                len(chapter.candidates) != count
                or {p.poseId for p in chapter.candidates} != expected
            ):
                problems.append(f"{chapter.chapterId}: 자세 {count}개와 chX-p1..pN ID가 필요하다")
            for pose in chapter.candidates:
                if not pose.animatable:
                    problems.append(f"{pose.poseId}: animatable은 true다")
                if not pose.outfit.strip():
                    problems.append(f"{pose.poseId}: outfit을 쓴다")
                problems.extend(hands_problems(pose.hands))
        return problems

    return check


def codex_checks(stage: str, workspace: Path) -> tuple[str, list]:
    inputs = workspace / "inputs"
    guard = read_json(inputs / "name-guard.json")
    if stage == "s4b-scene":
        return "scene-writer-output-v1", [
            check_scenes(read_json(inputs / "chosen-backgrounds.json"), guard)
        ]
    if stage == "s4b-pose":
        settings = read_json(inputs / "settings.json")
        return "pose-candidates-output-v1", [
            check_poses(settings["count"], guard, settings.get("chapters", CHAPTERS))
        ]
    raise ValueError(f"지원하지 않는 검사 단계: {stage}")


def _scene_example(chosen: list[dict]) -> dict:
    return {
        "chapters": [
            {
                "chapterId": ch["chapterId"],
                "source": ch["source"],
                "candidateId": ch.get("candidateId"),
                "place": ch.get("candidate", {}).get("place", "동네 산책길"),
                "timeOfDay": "저녁",
                "props": [],
                "mood": "저녁의 자연광",
                "sceneFacts": ["빈 벤치가 있다", "가로등이 켜졌다"],
                "meetingContext": "앞서 정한 약속으로 만났다",
                "relationshipCanon": []
                if ch["chapterId"] == "ch1"
                else ["앞선 만남에서 약속을 잡았다"],
                "sceneBoundaries": ["아직 연인이라고 부르지 않는다"],
                "plateBrief": "Empty neighborhood walkway, no people.",
            }
            for ch in chosen
        ]
    }


def _pose_example(count: int, chapters=CHAPTERS) -> dict:
    return {
        "chapters": [
            {
                "chapterId": ch,
                "candidates": [
                    {
                        "poseId": f"{ch}-p{i}",
                        "title": f"자세 {i}",
                        "body": "편안하게 앉는다",
                        "hands": "두 손을 무릎에 둔다",
                        "props": "",
                        "gaze": "상대를 본다",
                        "expression": "작게 웃는다",
                        "shot": "세로 9:16 허리 위 샷",
                        "outfit": "셔츠와 긴 바지",
                        "motionHint": "고개를 살짝 끄덕인다",
                        "animatable": True,
                    }
                    for i in range(1, count + 1)
                ],
            }
            for ch in chapters
        ]
    }


def rework_scope(ctx: Context, cid: str) -> tuple[ReworkBrief | None, Path | None, list[str]]:
    """G4b 수정 요청이면 (브리프, 직전 rev 폴더, 다시 만들 챕터), 아니면 (None, None, 전부)."""
    brief = load_rework(ctx, cid, "G4b")
    if brief is None:
        return None, None, list(CHAPTERS)
    previous = ctx.character_dir(cid) / "s4b-poses" / brief.fromRev
    if (
        not (previous / "scene-plan.json").exists()
        or not (previous / "pose-candidates.json").exists()
    ):
        return None, None, list(CHAPTERS)
    fields = {t.field for t in brief.targets}
    regenerate = [ch for ch in CHAPTERS if ch in fields]
    if not regenerate:
        return None, None, list(CHAPTERS)
    return brief, previous, regenerate


def revision_input(brief: ReworkBrief) -> dict:
    return {
        "gate": brief.gate,
        "round": brief.round,
        "targets": [t.field for t in brief.targets],
        "notes": {t.field: t.note for t in brief.targets},
        "instructions": brief.instructions,
        "keep": brief.keep,
    }


def carry_scene_chapter(src_dir: Path, chapter, rev_dir: Path) -> dict:
    """직전 revision의 장면 사실·배경 사진·자동 검사 보고서를 바이트 그대로 이월한다."""
    carried = dump(chapter)
    plate = carried["plate"]
    src = src_dir / plate["path"]
    if sha256_file(src) != plate["sha256"]:
        raise CheckFailed("s4b", [f"{plate['path']} 해시가 직전 revision과 다르다"])
    write_once_bytes(rev_dir / plate["path"], src.read_bytes())
    raw_qa = carried.get("qa")
    if raw_qa:
        carry_qa(src_dir, rev_dir, QaSummary.model_validate(raw_qa))
    return carried


def run_s4b(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s4b")
    backgrounds, selection, bg_dir = load_background_selection(ctx, cid)
    plan, _ = load_approved_plan_v2(ctx, cid)
    if backgrounds.planRev != plan.planRev:
        raise CheckFailed("s4b", ["G3 기획이 바뀌었다. S4a에서 배경을 다시 고른다"])
    appearance, _ = load_appearance_spec(ctx, cid)
    cfg = s4b_config(ctx)
    brief, previous, regenerate = rework_scope(ctx, cid)
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx, len(backgrounds.chapters)))
    settings = qa_settings(ctx)
    warning = ensure_judge(ctx, settings)
    rev = next_rev(ctx.character_dir(cid) / "s4b-poses", "ps")
    rev_dir = ctx.character_dir(cid) / "s4b-poses" / rev
    state.transition("s4b", "RUNNING", rev=rev)
    try:
        guard = ranking_guard(ctx, cid, appearance.sourceReferenceRev)
        chosen = []
        by_chapter = {ch.chapterId: ch for ch in backgrounds.chapters}
        for arc in plan.chapterArc:
            if arc.chapterId not in by_chapter:
                continue
            chapter = arc.chapterId
            if chapter in selection.picks:
                candidate = next(
                    c
                    for c in by_chapter[chapter].candidates
                    if c.candidateId == selection.picks[chapter]
                )
                chosen.append(
                    {
                        "chapterId": chapter,
                        "source": "CANDIDATE",
                        "candidateId": candidate.candidateId,
                        "candidate": dump(candidate),
                    }
                )
            else:
                chosen.append(
                    {
                        "chapterId": chapter,
                        "source": "USER",
                        "customText": selection.custom[chapter],
                    }
                )
        scene_inputs = {
            "plan-summary": plan_summary(plan),
            "chosen-backgrounds": chosen,
            "name-guard": guard,
        }
        if brief is not None:
            scene_inputs["revision"] = revision_input(brief)
        scene = call_agent(
            ctx,
            cid,
            budget,
            "s4b-scene",
            "scene_writer",
            "scene-writer-output-v1",
            rev_dir / "workspace-scene",
            scene_inputs,
            [check_scenes(chosen, guard)],
            _scene_example(chosen),
        )
        prior_scene: dict[str, object] = {}
        if previous is not None:
            prev_plan = validate("scene-plan-v1", read_json(previous / "scene-plan.json"))
            prior_scene = {ch.chapterId: ch for ch in prev_plan.chapters}
        fresh_scene = {ch.chapterId: ch for ch in scene.chapters}
        chapters = []
        for chapter_id in by_chapter:
            if previous is not None and chapter_id not in regenerate:
                chapters.append(carry_scene_chapter(previous, prior_scene[chapter_id], rev_dir))
                continue
            chapter = fresh_scene[chapter_id]
            picked = next(ch for ch in chosen if ch["chapterId"] == chapter.chapterId)
            plate = picked.get("candidate", {}).get("plate")
            if plate:
                src = bg_dir / plate["path"]
                if sha256_file(src) != plate["sha256"]:
                    raise CheckFailed("s4b", ["선택한 배경 plate의 해시가 다르다"])
                rel = f"plates/{chapter.chapterId}.png"
                write_once_bytes(rev_dir / rel, src.read_bytes())
                resolved = {"id": plate["id"], "path": rel, "sha256": plate["sha256"]}
                raw_qa = picked["candidate"].get("qa")
                qa = QaSummary.model_validate(raw_qa) if raw_qa else None
                carry_qa(bg_dir, rev_dir, qa)
            else:
                resolved, qa = make_plate(
                    ctx,
                    cid,
                    budget,
                    "s4b",
                    rev,
                    rev_dir,
                    chapter.chapterId,
                    chapter,
                    guard,
                    settings,
                    warning,
                )
            chapters.append(dump(chapter) | {"plate": resolved, "qa": dump(qa) if qa else None})
        scene_plan = validate(
            "scene-plan-v1",
            {
                "characterId": cid,
                "sceneRev": rev,
                "backgroundRev": backgrounds.backgroundRev,
                "planRev": plan.planRev,
                "aspectRatio": "9:16",
                "chapters": chapters,
            },
        )
        write_once_json(rev_dir / "scene-plan.json", dump(scene_plan))
        pose_inputs = {
            "scene-plan": dump(scene_plan),
            "chapterArc": [dump(c) for c in plan.chapterArc if c.chapterId in by_chapter],
            "personality": {
                "coreTraits": plan.coreTraits,
                "contrastTrait": plan.contrastTrait,
                "choices": [dump(c) for c in plan.choices],
            },
            "settings": {"count": cfg["candidates_per_chapter"], "chapters": list(by_chapter)},
            "name-guard": guard,
        }
        if brief is not None:
            pose_inputs["revision"] = revision_input(brief)
        pose_out = call_agent(
            ctx,
            cid,
            budget,
            "s4b-pose",
            "pose_director",
            "pose-candidates-output-v1",
            rev_dir / "workspace-pose",
            pose_inputs,
            [check_poses(cfg["candidates_per_chapter"], guard, by_chapter)],
            _pose_example(cfg["candidates_per_chapter"], by_chapter),
        )
        prior_pose: dict[str, object] = {}
        if previous is not None:
            prev_pose_set = validate(
                "pose-candidates-v1", read_json(previous / "pose-candidates.json")
            )
            prior_pose = {ch.chapterId: ch for ch in prev_pose_set.chapters}
        fresh_pose = {ch.chapterId: ch for ch in pose_out.chapters}
        pose_chapters = []
        for chapter_id in by_chapter:
            if previous is not None and chapter_id not in regenerate:
                pose_chapters.append(dump(prior_pose[chapter_id]))
            else:
                pose_chapters.append(dump(fresh_pose[chapter_id]))
        pose_set = validate(
            "pose-candidates-v1",
            {
                "characterId": cid,
                "sceneRev": rev,
                "chapters": pose_chapters,
            },
        )
        assert_no_names(scene_plan, guard)
        assert_no_names(pose_set, guard)
        write_once_json(rev_dir / "pose-candidates.json", dump(pose_set))
        write_once_text(rev_dir / "gate-G4b.html", render_g4b_page(cid, rev, scene_plan, pose_set))
        write_manifest(rev_dir)
    except FactoryError as e:
        ctx.state(cid).transition("s4b", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s4b", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G4b", "AWAITING_HUMAN", rev, None)
    return rev_dir
