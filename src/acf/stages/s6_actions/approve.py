"""G5b에서 동작마다 후보를 선택·제외하거나 수정을 요청한다."""

from __future__ import annotations

from pathlib import Path

from acf.common.errors import FactoryError, GateNotApprovedError
from acf.common.schema import dump, validate
from acf.common.store import read_json, write_manifest, write_once_json
from acf.contracts.video import ActionClip, ActionInputs, ApprovedActions
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record
from acf.stages.s4a_backgrounds.approve import answer_details


def load_clips(rev_dir: Path) -> list[ActionClip]:
    return [validate("action-clip-v2", obj) for obj in read_json(rev_dir / "clips.json")]


def _choices(answer: dict, clips: list[ActionClip]) -> tuple[dict[str, str], list[str]]:
    options: dict[str, set[str]] = {}
    for clip in clips:
        options.setdefault(clip.actionId, set()).add(clip.asset.candidateId)
    picks, excluded = answer.get("picks", {}), answer.get("excluded", [])
    if not isinstance(picks, dict) or not isinstance(excluded, list):
        raise FactoryError("G5b: picks는 객체, excluded는 actionId 목록이어야 한다")
    if any(not isinstance(a, str) for a in excluded) or len(excluded) != len(set(excluded)):
        raise FactoryError("G5b: excluded에는 중복 없는 actionId 문자열만 담는다")
    if set(picks) & set(excluded) or set(picks) | set(excluded) != set(options):
        raise FactoryError("G5b: 모든 동작을 picks 또는 excluded 중 정확히 하나에 담는다")
    for aid, candidate in picks.items():
        if not isinstance(candidate, str) or candidate not in options[aid]:
            raise FactoryError(f"G5b: {aid}에 속하지 않는 영상 후보를 골랐다")
    if {c.chapterId for c in clips if c.actionId in picks} != {"ch1", "ch2", "ch3"}:
        raise FactoryError("G5b: 챕터마다 하나 이상의 동작 영상을 남겨야 한다")
    return dict(picks), list(excluded)


def _changes(answer: dict, ids: set[str]) -> list[dict[str, str]]:
    changes = answer.get("requestedChanges")
    if not isinstance(changes, list) or not changes:
        raise FactoryError("G5b: requestedChanges에 수정할 동작과 note를 적는다")
    seen = set()
    for change in changes:
        if (
            not isinstance(change, dict)
            or set(change) != {"field", "note"}
            or not isinstance(change["field"], str)
            or change["field"] not in ids
            or change["field"] in seen
            or not isinstance(change["note"], str)
            or not change["note"].strip()
        ):
            raise FactoryError("G5b: 중복 없는 기존 actionId와 비어 있지 않은 note가 필요하다")
        seen.add(change["field"])
    return [{"field": c["field"], "note": c["note"].strip()} for c in changes]


def approve_g5b(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G5b")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G5b가 대기 상태가 아니다({gate.status})")
    details = answer_details(answer)
    rev_dir = ctx.character_dir(cid) / "s6-actions" / gate.rev
    clips = load_clips(rev_dir)
    decision = answer["decision"]
    picks, excluded, changes = {}, [], []
    approved = None
    if decision in {"APPROVE", "SELECT"}:
        choices = (
            {"picks": {c.actionId: "v1" for c in clips}, "excluded": []}
            if decision == "APPROVE"
            else answer
        )
        picks, excluded = _choices(choices, clips)
        decision = "SELECT"
        inputs: ActionInputs = validate("action-inputs-v2", read_json(rev_dir / "inputs.json"))
        specs = {a.actionId: a for ch in inputs.chapters for a in ch.actions}
        approved = validate(
            "action-videos-approved-v2",
            {
                "characterId": cid,
                "actionRev": gate.rev,
                "frameRev": inputs.frameRev,
                "appearanceRev": inputs.appearanceRev,
                "planRev": inputs.planRev,
                "excluded": excluded,
                "notes": details["reasons"],
                "clips": [
                    {
                        "actionId": c.actionId,
                        "chapterId": c.chapterId,
                        "stage": int(c.chapterId[2]),
                        "clipKey": specs[c.actionId].actionKey,
                        "playType": c.playType,
                        "mood": c.mood,
                        "pickRole": specs[c.actionId].pickRole,
                        "actionCategory": specs[c.actionId].actionCategory,
                        "title": specs[c.actionId].title,
                        "description": specs[c.actionId].description,
                        "useWhen": specs[c.actionId].useWhen,
                        "duration": specs[c.actionId].duration,
                        "videoId": c.asset.videoId,
                        "video": {
                            "id": c.asset.candidateId,
                            "path": c.asset.filePath,
                            "sha256": c.asset.fileSha256,
                        },
                    }
                    for c in clips
                    if picks.get(c.actionId) == c.asset.candidateId
                ],
            },
        )
    elif decision == "REQUEST_CHANGES":
        changes = _changes(answer, {c.actionId for c in clips})
    elif decision != "REJECT":
        raise FactoryError("G5b 결정은 SELECT·APPROVE·REQUEST_CHANGES·REJECT 중 하나다")
    rec = write_gate_record(
        ctx.character_dir(cid),
        state,
        gate="G5b",
        rev=gate.rev,
        stage_id="s6",
        shown=[rev_dir / "clips.json", rev_dir / "gate-G5b.html"],
        decision=decision,
        selections=[f"{aid}:{candidate}" for aid, candidate in picks.items()],
        requested_changes=changes,
        **details,
    )
    ctx.ledger(cid).record_human(gate="G5b", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    if approved:
        write_once_json(rev_dir / "approved-actions.json", dump(approved))
    write_manifest(rev_dir)
    return rev_dir


def load_approved_actions(ctx: Context, cid: str) -> tuple[ApprovedActions, Path]:
    """G5b에서 고른 동작 영상 묶음과 그 파일들의 기준 폴더를 돌려준다."""
    gate = ctx.state(cid).gate("G5b")
    if gate.status != "APPROVED" or not gate.rev:
        raise GateNotApprovedError(f"{cid}: G5b 승인이 필요하다(현재 {gate.status})")
    rev_dir = ctx.character_dir(cid) / "s6-actions" / gate.rev
    path = rev_dir / "approved-actions.json"
    if not path.exists():
        raise GateNotApprovedError(f"{cid}: G5b가 동작 영상을 고르지 않았다")
    return validate("action-videos-approved-v2", read_json(path)), rev_dir
