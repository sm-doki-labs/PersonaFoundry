"""G6 승인 → persona_version 발급 (FR-23)."""

from __future__ import annotations

import json
from pathlib import Path

from acf.common.schema import dump, validate
from acf.common.store import write_manifest, write_once_json
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record


def approve_g6(ctx: Context, cid: str, answer: dict) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    rev = state.gate("G6").rev
    if not rev or state.gate("G6").status != "AWAITING_HUMAN":
        raise ValueError(f"{cid}: G6가 대기 상태가 아니다({state.gate('G6').status})")
    rev_dir = char_dir / "s8-prompts" / rev
    shown = [rev_dir / "prompt-pair.json", rev_dir / "prompt-probe.json"]
    tr = state.stage("s7").currentRev
    if tr:
        shown.append(char_dir / "s7-traits" / tr / "trait-sheet.json")
    rec = write_gate_record(
        char_dir,
        state,
        gate="G6",
        rev=rev,
        stage_id="s8",
        shown=shown,
        decision=answer["decision"],
        reviewer=answer["reviewer"],
        reasons=answer.get("reasons", ""),
        minutes=float(answer.get("minutes", 0)),
        requested_changes=answer.get("requestedChanges"),
    )
    ctx.ledger(cid).record_human(gate="G6", minutes=rec.minutes, ref=f"{cid}/{rev}")
    if rec.decision == "APPROVE":
        pair = validate(
            "prompt-pair-v1", json.loads((rev_dir / "prompt-pair.json").read_text("utf-8"))
        )
        pair = pair.model_copy(update={"personaVersion": rev})
        write_once_json(rev_dir / "persona-version.json", dump(pair))
        if tr and state.stage("s7").status == "AWAITING_HUMAN":
            state.transition("s7", "APPROVED", rev=tr)
        write_manifest(rev_dir)
    return rev_dir
