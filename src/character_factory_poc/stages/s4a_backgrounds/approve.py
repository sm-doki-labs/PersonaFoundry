"""G4a 배경 선택과 직접 정의를 revision에 고정한다."""

from __future__ import annotations

import math
from pathlib import Path

from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_manifest, write_once_json
from character_factory_poc.contracts.scene import CHAPTERS, BackgroundSelection, BackgroundSet
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record


def answer_details(answer: dict) -> dict:
    if not isinstance(answer, dict) or not isinstance(answer.get("decision"), str):
        raise FactoryError("관문 답은 문자열 decision을 담은 객체여야 한다")
    reviewer = answer.get("reviewer", "user")
    reasons = answer.get("reasons", "")
    if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(reasons, str):
        raise FactoryError("reviewer와 reasons는 문자열이어야 한다")
    try:
        minutes = float(answer.get("minutes", 0))
    except (TypeError, ValueError) as e:
        raise FactoryError("minutes는 0 이상의 숫자다") from e
    if not math.isfinite(minutes) or minutes < 0:
        raise FactoryError("minutes는 0 이상의 유한한 숫자다")
    return {"reviewer": reviewer, "reasons": reasons, "minutes": minutes}


def validate_choices(answer: dict, options: dict[str, set[str]], gate: str) -> tuple[dict, dict]:
    picks, custom = answer.get("picks", {}), answer.get("custom", {})
    if not isinstance(picks, dict) or not isinstance(custom, dict):
        raise FactoryError(f"{gate}: picks·custom은 챕터를 키로 하는 객체다")
    if set(picks) & set(custom) or set(picks) | set(custom) != set(options):
        raise FactoryError(f"{gate}: 요청한 장면마다 후보나 직접 정한 장소를 하나씩 골라 주세요.")
    for chapter, value in picks.items():
        if not isinstance(value, str) or value not in options[chapter]:
            raise FactoryError(f"{gate}: {chapter}에 속하지 않는 후보를 골랐다")
    if any(not isinstance(text, str) or not text.strip() for text in custom.values()):
        raise FactoryError(f"{gate}: custom은 빈 문자열일 수 없다")
    return dict(picks), {ch: text.strip() for ch, text in custom.items()}


def validate_requested_changes(answer: dict, gate: str) -> list[dict[str, str]]:
    """챕터별 수정 요청(LLD §6.9). s4_frames/approve.py의 G4 검사와 같은 규칙이다."""
    changes = answer.get("requestedChanges")
    if changes is None:
        # 옛 답 형식: 챕터를 고르지 않고 reasons에 고칠 점만 적는다. 재작업 브리프는 이유를
        # 단일 메모로 받아 전체를 다시 만든다.
        reasons = answer.get("reasons")
        if not isinstance(reasons, str) or not reasons.strip():
            raise FactoryError(
                f"{gate}: REQUEST_CHANGES에는 챕터별 requestedChanges 또는 "
                "고칠 점 reasons가 필요하다"
            )
        return []
    if not isinstance(changes, list) or not changes:
        raise FactoryError(f"{gate}: requestedChanges에 수정할 챕터와 note를 적는다")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
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
                f"{gate}: requestedChanges는 중복 없는 ch1·ch2·ch3와 비어 있지 않은 note가 필요하다"
            )
        seen.add(change["field"])
        out.append({"field": change["field"], "note": change["note"]})
    return out


def approve_g4a(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G4a")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G4a가 대기 상태가 아니다({gate.status})")
    rev_dir = ctx.character_dir(cid) / "s4a-backgrounds" / gate.rev
    backgrounds = validate(
        "background-candidates-v1", read_json(rev_dir / "background-candidates.json")
    )
    details = answer_details(answer)
    decision = answer.get("decision")
    selected = None
    selections = []
    changes: list[dict[str, str]] = []
    if decision in {"SELECT", "APPROVE"}:
        options = {
            ch.chapterId: {c.candidateId for c in ch.candidates} for ch in backgrounds.chapters
        }
        choices = (
            answer
            if decision == "SELECT"
            else {
                "picks": {ch: f"{ch}-b1" for ch in options},
            }
        )
        picks, custom = validate_choices(choices, options, "G4a")
        selected = BackgroundSelection(backgroundRev=gate.rev, picks=picks, custom=custom)
        selections = list(picks.values()) + [f"custom:{ch}" for ch in custom]
    elif decision == "REQUEST_CHANGES":
        changes = validate_requested_changes(answer, "G4a")
    elif decision != "REJECT":
        raise FactoryError("G4a 결정은 SELECT·APPROVE·REQUEST_CHANGES·REJECT 중 하나다")
    if selected:
        write_once_json(rev_dir / "selection.json", dump(selected))
    rec = write_gate_record(
        ctx.character_dir(cid),
        state,
        gate="G4a",
        rev=gate.rev,
        stage_id="s4a",
        shown=[rev_dir / "background-candidates.json", rev_dir / "gate-G4a.html"],
        decision=decision,
        selections=selections,
        requested_changes=changes,
        **details,
    )
    ctx.ledger(cid).record_human(gate="G4a", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    write_manifest(rev_dir)
    return rev_dir


def load_background_selection(
    ctx: Context, cid: str
) -> tuple[BackgroundSet, BackgroundSelection, Path]:
    gate = ctx.state(cid).gate("G4a")
    if gate.status != "APPROVED" or not gate.rev:
        raise GateNotApprovedError(f"{cid}: G4a 승인이 필요하다(현재 {gate.status})")
    rev_dir = ctx.character_dir(cid) / "s4a-backgrounds" / gate.rev
    if not (rev_dir / "selection.json").exists():
        raise GateNotApprovedError(f"{cid}: G4a 배경 선택이 없다")
    return (
        validate("background-candidates-v1", read_json(rev_dir / "background-candidates.json")),
        validate("background-selection-v1", read_json(rev_dir / "selection.json")),
        rev_dir,
    )
