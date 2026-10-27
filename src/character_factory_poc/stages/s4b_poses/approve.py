"""G4b 선택·직접 정의·필드 수정을 최종 pose-plan으로 고정한다."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_manifest, write_once_json
from character_factory_poc.contracts.scene import (
    CHAPTERS,
    POSE_FIELDS,
    PosePlan,
    PoseSelection,
    ScenePlan,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record
from character_factory_poc.stages.s4a_backgrounds.approve import (
    answer_details,
    validate_choices,
    validate_requested_changes,
)
from character_factory_poc.stages.s4b_poses.run import hands_problems


def approve_g4b(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G4b")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G4b가 대기 상태가 아니다({gate.status})")
    rev_dir = ctx.character_dir(cid) / "s4b-poses" / gate.rev
    poses = validate("pose-candidates-v1", read_json(rev_dir / "pose-candidates.json"))
    details = answer_details(answer)
    decision = answer.get("decision")
    selections = []
    selected = resolved = None
    changes: list[dict[str, str]] = []
    if decision in {"SELECT", "APPROVE"}:
        by_chapter = {ch.chapterId: {p.poseId: p for p in ch.candidates} for ch in poses.chapters}
        options = {ch: set(candidates) for ch, candidates in by_chapter.items()}
        choices = answer if decision == "SELECT" else {"picks": {ch: f"{ch}-p1" for ch in CHAPTERS}}
        picks, custom = validate_choices(choices, options, "G4b")
        tweaks = choices.get("tweaks", {})
        if not isinstance(tweaks, dict) or not set(tweaks) <= set(picks):
            raise FactoryError("G4b: tweaks는 고른 챕터에만 쓸 수 있다")
        for change in tweaks.values():
            if not isinstance(change, dict) or not set(change) <= set(POSE_FIELDS):
                raise FactoryError("G4b: tweaks는 POSE_FIELDS 항목만 고칠 수 있다")
            if any(not isinstance(value, str) for value in change.values()):
                raise FactoryError("G4b: 수정할 값은 문자열이어야 한다")
        chapters = []
        for chapter in CHAPTERS:
            if chapter in custom:
                chapters.append(
                    {"chapterId": chapter, "source": "USER", "customText": custom[chapter]}
                )
                continue
            pose = dump(by_chapter[chapter][picks[chapter]])
            pose.pop("animatable")
            changes = tweaks.get(chapter, {})
            pose.update(changes)
            if any(
                not pose[field].strip()
                for field in (
                    "body",
                    "hands",
                    "gaze",
                    "expression",
                    "shot",
                    "outfit",
                    "motionHint",
                )
            ) or hands_problems(pose["hands"]):
                raise FactoryError("G4b: 필수 자세 항목을 비우거나 손을 얼굴에 닿게 할 수 없다")
            chapters.append(
                pose
                | {
                    "chapterId": chapter,
                    "source": "CANDIDATE",
                    "tweaked": [f for f in POSE_FIELDS if f in changes],
                }
            )
        selected = PoseSelection(sceneRev=gate.rev, picks=picks, custom=custom, tweaks=tweaks)
        resolved = validate(
            "pose-plan-v1", {"characterId": cid, "sceneRev": gate.rev, "chapters": chapters}
        )
        selections = list(picks.values()) + [f"custom:{ch}" for ch in custom]
    elif decision == "REQUEST_CHANGES":
        changes = validate_requested_changes(answer, "G4b")
    elif decision != "REJECT":
        raise FactoryError("G4b 결정은 SELECT·APPROVE·REQUEST_CHANGES·REJECT 중 하나다")
    if selected:
        write_once_json(rev_dir / "selection.json", dump(selected))
        write_once_json(rev_dir / "pose-plan.json", dump(resolved))
    rec = write_gate_record(
        ctx.character_dir(cid),
        state,
        gate="G4b",
        rev=gate.rev,
        stage_id="s4b",
        shown=[
            rev_dir / "scene-plan.json",
            rev_dir / "pose-candidates.json",
            rev_dir / "gate-G4b.html",
        ],
        decision=decision,
        selections=selections,
        requested_changes=changes,
        **details,
    )
    ctx.ledger(cid).record_human(gate="G4b", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    write_manifest(rev_dir)
    return rev_dir


def load_scene_and_pose(ctx: Context, cid: str) -> tuple[ScenePlan, PosePlan, Path]:
    gate = ctx.state(cid).gate("G4b")
    if gate.status != "APPROVED" or not gate.rev:
        raise GateNotApprovedError(f"{cid}: G4b 승인이 필요하다(현재 {gate.status})")
    rev_dir = ctx.character_dir(cid) / "s4b-poses" / gate.rev
    if not (rev_dir / "pose-plan.json").exists():
        raise GateNotApprovedError(f"{cid}: G4b 자세 선택이 없다")
    return (
        validate("scene-plan-v1", read_json(rev_dir / "scene-plan.json")),
        validate("pose-plan-v1", read_json(rev_dir / "pose-plan.json")),
        rev_dir,
    )
