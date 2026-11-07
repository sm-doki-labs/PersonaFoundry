"""수정 요청 재작업 (LLD §5.20·§6.9, 명세 §7.3, D-0049, FR-46).

관문 결정이 `REQUEST_CHANGES`이면 실행기가 단계를 다시 돌리기 전에 `prepare_rework`를 부른다.
사람 메모를 `rework-brief-v1`로 한 번만 고정하고, 단계 실행 함수는 시작할 때 `load_rework`로
브리프를 읽어 요청한 부분만 새 revision으로 다시 만든다. 같은 관문의 수정 요청이 `[rework]
max_rounds`를 넘으면 사람이 `RunOptions.confirmed`로 허락할 때까지 다시 만들지 않는다.

반려(`REJECT`)는 메모가 없는 결정이므로 브리프를 쓰지 않는다(명세 §7.3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.rework import NormalizerRef, ReworkBrief, ReworkTarget
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import now_iso
from character_factory_poc.pipeline.graph import STAGES
from character_factory_poc.providers.base import ChatRequest, Message

if TYPE_CHECKING:
    from character_factory_poc.pipeline.orchestrator import RunOptions

# 명세 §7.3: G3는 화면에서 칸을 직접 고치므로 재작업 대상이 아니다.
REWORK_GATES = frozenset({"G1", "G4a", "G4b", "G4", "G5", "G5b", "G6"})
CHAPTERS = ("ch1", "ch2", "ch3")
DEFAULTS: dict[str, Any] = {"max_rounds": 3, "normalize": True}

# 관문 기록이 requestedChanges 대신 reasons에 메모를 담는 관문(화면이 그렇게 낸다).
# 브리프의 targets는 requestedChanges 원문을 먼저 쓰고, 없을 때만 이 단위 이름으로 메모를 담는다.
FALLBACK_UNIT = {
    "G1": "previews",
    "G4a": "chapters",
    "G4b": "chapters",
    "G4": "chapters",
    "G5": "candidates",
    "G5b": "actions",
    "G6": "promptPair",
}

ROLE = (
    "너는 캐릭터 공장의 재작업 지시 작성자다. 사람이 남긴 수정 메모를 그대로 살리면서, "
    "단계 에이전트가 바로 따를 수 있는 짧은 지시문 한두 문장으로 바꾼다. 메모에 없는 요구를 "
    "더하지 않고, 새 사실·이름·수치를 만들지 않는다. 지시문만 출력한다. "
    "목록·머리말·설명은 붙이지 않는다."
)


def rework_config(ctx: Context) -> dict[str, Any]:
    return DEFAULTS | dict(ctx.config.rework)


def max_rounds(config: dict[str, Any] | None) -> int:
    cfg = DEFAULTS | dict(config or {})
    try:
        value = int(cfg["max_rounds"])
    except (TypeError, ValueError):
        return int(DEFAULTS["max_rounds"])
    return value if value >= 1 else int(DEFAULTS["max_rounds"])


def rework_dir(char_dir: Path) -> Path:
    return Path(char_dir) / "rework"


def brief_path(char_dir: Path, gate: str, rev: str) -> Path:
    return rework_dir(char_dir) / f"{gate}-{rev}.json"


def gate_records(char_dir: Path, gate: str) -> list[dict[str, Any]]:
    """그 관문의 결정 기록을 파일 이름 순서로 읽는다. 깨진 파일은 건너뛴다."""
    folder = Path(char_dir) / "gates"
    if not folder.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(folder.glob(f"{gate}-*.json")):
        try:
            out.append(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError):
            continue
    return out


def rework_rounds(char_dir: Path, gate: str) -> int:
    """그 관문의 `REQUEST_CHANGES` 결정 수. 이번 수정 요청도 포함한다(LLD §5.20)."""
    return sum(
        1 for rec in gate_records(char_dir, gate) if rec.get("decision") == "REQUEST_CHANGES"
    )


def rework_status(
    char_dir: Path, gate: str, config: dict[str, Any] | None
) -> dict[str, Any] | None:
    """화면용 수정 차수. 재작업 관문이 아니면 None이다."""
    if gate not in REWORK_GATES:
        return None
    rounds = rework_rounds(char_dir, gate)
    limit = max_rounds(config)
    return {"round": rounds, "maxRounds": limit, "capReached": rounds >= limit}


def _current_record(ctx: Context, cid: str, gate: str) -> tuple[dict[str, Any] | None, str, str]:
    """관문 상태가 가리키는 마지막 결정 기록과 (rev, 캐릭터 폴더 기준 경로)를 돌려준다."""
    g = ctx.state(cid).gate(gate)
    rev = g.rev or ""
    if not rev or not g.recordRef:
        return None, rev, ""
    path = ctx.character_dir(cid) / g.recordRef
    if not path.exists():
        return None, rev, ""
    try:
        return read_json(path), rev, g.recordRef
    except (OSError, ValueError):
        return None, rev, ""


def _targets(record: dict[str, Any], gate: str) -> list[ReworkTarget]:
    """requestedChanges 원문. 비어 있으면 reasons 메모를 단일 대상으로 담는다."""
    out: list[ReworkTarget] = []
    for change in record.get("requestedChanges") or []:
        if not isinstance(change, dict):
            continue
        field, note = change.get("field"), change.get("note")
        if isinstance(field, str) and field.strip() and isinstance(note, str) and note.strip():
            out.append(ReworkTarget(field=field, note=note))
    if out:
        return out
    reasons = record.get("reasons")
    if isinstance(reasons, str) and reasons.strip():
        return [ReworkTarget(field=FALLBACK_UNIT.get(gate, "all"), note=reasons.strip())]
    return []


def _keep_units(
    ctx: Context, cid: str, gate: str, rev: str, targets: list[ReworkTarget]
) -> list[str]:
    """다시 만들지 않고 직전 revision에서 그대로 이월할 단위 ID."""
    fields = {t.field for t in targets}
    if gate in {"G4a", "G4b", "G4"}:
        return [ch for ch in CHAPTERS if ch not in fields]
    if gate == "G5b":
        return _action_ids(ctx, cid, rev, fields)
    if gate == "G1":
        return [] if "previews" in fields else ["previews"]
    return []


def _action_ids(ctx: Context, cid: str, rev: str, fields: set[str]) -> list[str]:
    """직전 s6 revision의 inputs.json에서 동작 ID를 읽어 대상이 아닌 것만 남긴다."""
    if not rev:
        return []
    path = ctx.character_dir(cid) / "s6-actions" / rev / "inputs.json"
    if not path.exists():
        return []
    try:
        inputs = read_json(path)
    except (OSError, ValueError):
        return []
    out = []
    for chapter in inputs.get("chapters") or []:
        for action in chapter.get("actions") or []:
            action_id = action.get("actionId")
            if isinstance(action_id, str) and action_id not in fields:
                out.append(action_id)
    return out


def _raw_instruction(notes: list[str]) -> str:
    return "\n".join(notes)


def _instruct(
    ctx: Context, cid: str, sid: str, gate: str, rev: str, notes: list[str], config: dict[str, Any]
) -> tuple[str, NormalizerRef | None]:
    raw = _raw_instruction(notes)
    if not notes or not bool(config.get("normalize", True)):
        return raw, None
    try:
        model = (
            ctx.task_model(cid, ctx.budget(), "brief")
            if ctx.text_deck_enabled and sid in {"s3", "s7", "s8", "s9s", "s9"}
            else ctx.text_model(cid, ctx.budget())
        )
        resp = model.complete(
            ChatRequest(
                kind="REWORK",
                stage=sid,
                messages=(
                    Message("system", ROLE),
                    Message(
                        "user",
                        f"<gate>{gate}</gate>\n<stage>{sid}</stage>\n"
                        + "".join(f"<note>{n}</note>\n" for n in notes),
                    ),
                ),
                ref=f"{cid}/rework/{gate}-{rev}",
                max_output_tokens=600,
                temperature=0.2,
            )
        )
    except Exception:  # 공급자 실패는 재작업을 막지 않는다. 원문 메모로 돌아간다.
        return raw, None
    text = (resp.text or "").strip()
    if not text:
        return raw, None
    return text, NormalizerRef(provider=resp.provider, model=resp.model)


def _write_brief(
    ctx: Context,
    cid: str,
    sid: str,
    gate: str,
    rev: str,
    record_ref: str,
    record: dict[str, Any],
    rounds: int,
) -> ReworkBrief | None:
    """브리프를 한 번만 쓴다. 이미 있으면 그대로 두고 읽어 돌려준다."""
    char_dir = ctx.character_dir(cid)
    path = brief_path(char_dir, gate, rev)
    if path.exists():
        return load_rework(ctx, cid, gate)
    targets = _targets(record, gate)
    config = rework_config(ctx)
    instructions, normalized_by = _instruct(
        ctx, cid, sid, gate, rev, [t.note for t in targets], config
    )
    brief: ReworkBrief = validate(  # type: ignore[assignment]
        "rework-brief-v1",
        dump(
            ReworkBrief(
                subjectId=ctx.state(cid).state.subjectId,
                gate=gate,
                stage=sid,
                fromRev=rev,
                round=rounds,
                recordRef=record_ref,
                targets=targets,
                keep=_keep_units(ctx, cid, gate, rev, targets),
                instructions=instructions,
                normalizedBy=normalized_by,
                createdAt=now_iso(),
            )
        ),
    )
    write_once_json(path, dump(brief))
    return brief


def prepare_rework(ctx: Context, cid: str, sid: str, opt: RunOptions) -> bool:
    """REJECTED 단계를 다시 돌리기 직전에 부른다. False면 그 단계를 돌리지 않는다(반복 상한)."""
    stage = STAGES.get(sid)
    gate = stage.gate if stage else None
    if gate not in REWORK_GATES:
        return True
    record, rev, record_ref = _current_record(ctx, cid, gate)
    if record is None or record.get("decision") != "REQUEST_CHANGES":
        return True
    rounds = rework_rounds(ctx.character_dir(cid), gate)
    if rounds > max_rounds(rework_config(ctx)) and sid not in opt.confirmed:
        return False
    _write_brief(ctx, cid, sid, gate, rev, record_ref, record, max(rounds, 1))
    return True


def load_rework(ctx: Context, cid: str, gate: str) -> ReworkBrief | None:
    """관문 상태의 rev와 `fromRev`가 같은 브리프. 없거나 다른 rev면 None."""
    g = ctx.state(cid).gate(gate)
    if not g.rev:
        return None
    path = brief_path(ctx.character_dir(cid), gate, g.rev)
    if not path.exists():
        return None
    try:
        brief = validate("rework-brief-v1", read_json(path))
    except Exception:
        return None
    return brief if brief.fromRev == g.rev else None  # type: ignore[return-value]
