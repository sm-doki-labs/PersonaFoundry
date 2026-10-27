"""G9 결정: 사람이 릴리즈 패키지를 승인하거나 거절한다 (LLD §8.10)."""

from __future__ import annotations

from pathlib import Path

from acf.common.errors import FactoryError
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record


def _reasons(answer: dict) -> str:
    value = answer.get("reasons", "")
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip())
    return str(value)


def approve_g9(ctx: Context, cid: str, answer: dict) -> Path:
    """answer = {"decision": "APPROVE"|"REJECT", "reasons": str|[str]}."""
    state = ctx.state(cid)
    gate = state.gate("G9")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G9가 대기 상태가 아니다({gate.status})")
    decision = answer.get("decision")
    if decision not in {"APPROVE", "REJECT"}:
        raise FactoryError("G9 결정은 APPROVE·REJECT 중 하나다")
    rev_dir = ctx.character_dir(cid) / "s11-release" / gate.rev
    if not (rev_dir / "package.json").is_file():
        raise FactoryError(f"{cid}: {gate.rev}/package.json이 없다")
    rec = write_gate_record(
        ctx.character_dir(cid),
        state,
        gate="G9",
        rev=gate.rev,
        stage_id="s11",
        shown=[rev_dir / "package.json", rev_dir / "gate-G9.html"],
        decision=decision,
        reviewer=str(answer.get("reviewer") or "user"),
        reasons=_reasons(answer),
        minutes=float(answer.get("minutes", 0)),
    )
    ctx.ledger(cid).record_human(gate="G9", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    return rev_dir


def load_approved_package_dir(ctx: Context, cid: str) -> Path:
    """G9 승인이 있어야 변환기가 돈다(LLD §8.11)."""
    from acf.common.errors import GateNotApprovedError

    gate = ctx.state(cid).gate("G9")
    if gate.status != "APPROVED" or not gate.rev:
        raise GateNotApprovedError(f"{cid}: G9 승인이 필요하다(현재 {gate.status})")
    rev_dir = ctx.character_dir(cid) / "s11-release" / gate.rev
    if not (rev_dir / "package.json").is_file():
        raise GateNotApprovedError(f"{cid}: {gate.rev}/package.json이 없다")
    return rev_dir


__all__ = ["approve_g9", "load_approved_package_dir"]
