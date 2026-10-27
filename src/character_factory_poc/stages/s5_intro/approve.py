"""G5 결정: 사람이 소개 영상 후보 하나를 고른다 (명세 §7, LLD §8.5, D-0028)."""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import write_manifest, write_once_json
from character_factory_poc.contracts.video import ApprovedIntro, IntroInputs, VideoAsset
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record


def load_assets(rev_dir: Path) -> list[VideoAsset]:
    objs = json.loads((rev_dir / "videos.json").read_text("utf-8"))
    return [validate("video-asset-v1", o) for o in objs]  # type: ignore[misc]


def approve_g5(ctx: Context, cid: str, answer: dict) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    g = state.gate("G5")
    if g.status != "AWAITING_HUMAN" or not g.rev:
        raise FactoryError(f"{cid}: G5가 대기 상태가 아니다({g.status})")
    rev_dir = char_dir / "s5-intro" / g.rev
    assets = load_assets(rev_dir)
    ids = [a.candidateId for a in assets]
    decision = answer["decision"]
    selections = list(answer.get("selections") or [])
    reasons = answer.get("reasons", "")
    if decision == "APPROVE":  # --auto-approve G5 (D-0015)
        selections = selections or [ids[0]]
        decision = "SELECT"
    if decision == "SELECT":
        if len(selections) != 1 or selections[0] not in ids:
            raise FactoryError(
                f"G5 SELECT는 후보 하나를 selections에 담아야 한다({', '.join(ids)})"
            )
    elif decision in {"REJECT", "REQUEST_CHANGES"}:
        selections = []
    else:
        raise FactoryError(f"G5 결정은 SELECT·REQUEST_CHANGES·REJECT 중 하나다: {decision}")
    rec = write_gate_record(
        char_dir,
        state,
        gate="G5",
        rev=g.rev,
        stage_id="s5",
        shown=[rev_dir / "videos.json", rev_dir / "gate-G5.html"],
        decision=decision,
        reviewer=answer["reviewer"],
        reasons=reasons,
        selections=selections,
        minutes=float(answer.get("minutes", 0)),
        requested_changes=answer.get("requestedChanges"),
    )
    ctx.ledger(cid).record_human(gate="G5", minutes=rec.minutes, ref=f"{cid}/{g.rev}")
    if decision == "SELECT":
        chosen = next(a for a in assets if a.candidateId == selections[0])
        inputs: IntroInputs = validate(  # type: ignore[assignment]
            "intro-inputs-v2", json.loads((rev_dir / "inputs.json").read_text("utf-8"))
        )
        approved = validate(
            "intro-video-approved-v1",
            {
                "characterId": cid,
                "introRev": g.rev,
                "appearanceRev": inputs.appearanceRev,
                "videoId": chosen.videoId,
                "video": {
                    "id": chosen.candidateId,
                    "path": chosen.filePath,
                    "sha256": chosen.fileSha256,
                },
                "notes": reasons,
            },
        )
        write_once_json(rev_dir / "approved-intro.json", dump(approved))
        write_manifest(rev_dir)
    return rev_dir


def load_approved_intro(ctx: Context, cid: str) -> tuple[ApprovedIntro, Path]:
    """G5에서 고른 소개 영상(편집·릴리즈 입력)."""
    g = ctx.state(cid).gate("G5")
    if g.status != "APPROVED" or not g.rev:
        raise GateNotApprovedError(f"{cid}: G5 승인이 필요하다(현재 {g.status})")
    rev_dir = ctx.character_dir(cid) / "s5-intro" / g.rev
    p = rev_dir / "approved-intro.json"
    if not p.exists():
        raise GateNotApprovedError(f"{cid}: G5가 영상을 고르지 않았다")
    return validate("intro-video-approved-v1", json.loads(p.read_text("utf-8"))), rev_dir  # type: ignore[return-value]
