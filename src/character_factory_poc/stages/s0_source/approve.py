"""G0 출처 확인 (D-0120, D-0126, D-0128). 사람만 결정한다(자동 승인 불가)."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import validate
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record
from character_factory_poc.stages.s0_source.run import STAGE_DIR

DECISIONS = {"APPROVE", "REQUEST_CHANGES", "REJECT"}


def approve_g0(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G0")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G0이 대기 상태가 아니다({gate.status})")
    decision = answer.get("decision")
    if decision not in DECISIONS:
        raise FactoryError(f"G0 결정은 {', '.join(sorted(DECISIONS))} 중 하나다")
    char_dir = ctx.character_dir(cid)
    rev_dir = char_dir / STAGE_DIR / gate.rev
    index = validate("source-index-v1", read_json(rev_dir / "source-index.json"))
    if decision == "APPROVE" and index.usageProblems:  # type: ignore[attr-defined]
        raise FactoryError(
            "사용 근거가 비어 G0을 승인할 수 없다: " + "; ".join(index.usageProblems)  # type: ignore[attr-defined]
        )
    shown = [rev_dir / "source-index.json", rev_dir / "digest.json", rev_dir / "gate-G0.html"]
    facts = rev_dir / "facts.json"
    ids = set()
    if facts.exists():
        shown.append(facts)
        ids = {item["factId"] for item in read_json(facts)["items"]}
    exclusions = answer.get("excludedFactIds", [])
    if not isinstance(exclusions, list) or any(
        not isinstance(i, str) or i not in ids for i in exclusions
    ):
        raise FactoryError("제외할 사실 ID는 이 G0 목록에서 고른다")
    rec = write_gate_record(
        char_dir,
        state,
        gate="G0",
        rev=gate.rev,
        stage_id="s0",
        shown=shown,
        selections=exclusions,
        decision=decision,
        reviewer=answer.get("reviewer", "user"),
        reasons=answer.get("reasons", ""),
        minutes=answer.get("minutes", 0),
        requested_changes=answer.get("requestedChanges") or [],
    )
    ctx.ledger(cid).record_human(gate="G0", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    return rev_dir
