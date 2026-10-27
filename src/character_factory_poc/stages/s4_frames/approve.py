"""G4 결정과 승인한 f1 묶음. 기존 ApprovedFrames 계약과 로더를 유지한다."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_manifest, write_once_json
from character_factory_poc.contracts.frames import ApprovedFrames, ChapterFrame
from character_factory_poc.contracts.scene import CHAPTERS
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record
from character_factory_poc.stages.s4a_backgrounds.approve import answer_details


def load_frames(rev_dir: Path) -> list[ChapterFrame]:
    return [validate("chapter-frame-v1", obj) for obj in read_json(rev_dir / "frames.json")]


def approve_g4(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G4")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G4가 대기 상태가 아니다({gate.status})")
    rev_dir = ctx.character_dir(cid) / "s4-frames" / gate.rev
    frames = load_frames(rev_dir)
    by_id = {f.frameId: f for f in frames}
    details = answer_details(answer)
    decision = answer.get("decision")
    selections, changes = [], []
    approved = None
    if decision in {"APPROVE", "SELECT"}:
        selections = (
            [f"{ch}-f1" for ch in CHAPTERS]
            if decision == "APPROVE"
            else answer.get("selections", [])
        )
        if not isinstance(selections, list) or any(
            not isinstance(s, str) or s not in by_id for s in selections
        ):
            raise FactoryError("G4: 없는 프레임을 골랐다")
        if sorted(by_id[s].chapterId for s in selections) != list(CHAPTERS):
            raise FactoryError("G4: ch1·ch2·ch3에서 프레임을 하나씩 골라야 한다")
        picked = sorted((by_id[s] for s in selections), key=lambda f: f.chapterId)
        approved = validate(
            "chapter-frames-approved-v1",
            {
                "characterId": cid,
                "frameRev": gate.rev,
                "appearanceRev": picked[0].appearanceRev,
                "planRev": picked[0].planRev,
                "notes": details["reasons"],
                "frames": [
                    {
                        "chapterId": f.chapterId,
                        "frameId": f.frameId,
                        "path": f.filePath,
                        "sha256": sha256_file(rev_dir / f.filePath),
                        "prompt": f.prompt,
                    }
                    for f in picked
                ],
            },
        )
    elif decision == "REQUEST_CHANGES":
        changes = answer.get("requestedChanges")
        if not isinstance(changes, list) or not changes:
            raise FactoryError("G4: requestedChanges에 수정할 챕터와 note를 적는다")
        seen = set()
        for change in changes:
            if (
                not isinstance(change, dict)
                or set(change) != {"field", "note"}
                or not isinstance(change["field"], str)
                or change["field"] not in CHAPTERS
                or change["field"] in seen
                or not isinstance(change["note"], str)
                or not change["note"].strip()
            ):
                raise FactoryError(
                    "G4: requestedChanges는 중복 없는 ch1·ch2·ch3와 비어 있지 않은 note가 필요하다"
                )
            seen.add(change["field"])
    elif decision != "REJECT":
        raise FactoryError("G4 결정은 APPROVE·SELECT·REQUEST_CHANGES·REJECT 중 하나다")
    rec = write_gate_record(
        ctx.character_dir(cid),
        state,
        gate="G4",
        rev=gate.rev,
        stage_id="s4",
        shown=[rev_dir / "frames.json", rev_dir / "gate-G4.html"],
        decision=decision,
        selections=selections,
        requested_changes=changes,
        **details,
    )
    ctx.ledger(cid).record_human(gate="G4", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    if approved:
        write_once_json(rev_dir / "approved-frames.json", dump(approved))
    write_manifest(rev_dir)
    return rev_dir


def load_approved_frames(ctx: Context, cid: str) -> tuple[ApprovedFrames, Path]:
    gate = ctx.state(cid).gate("G4")
    if gate.status != "APPROVED" or not gate.rev:
        raise GateNotApprovedError(f"{cid}: G4 승인이 필요하다(현재 {gate.status})")
    rev_dir = ctx.character_dir(cid) / "s4-frames" / gate.rev
    path = rev_dir / "approved-frames.json"
    if not path.exists():
        raise GateNotApprovedError(f"{cid}: G4가 프레임을 고르지 않았다")
    return validate("chapter-frames-approved-v1", read_json(path)), rev_dir
