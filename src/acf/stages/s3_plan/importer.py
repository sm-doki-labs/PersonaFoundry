"""acf plan import (D-0013, LLD §4·§8.3). 사용자가 쓴 기획서를 character-plan-v1로 고정한다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acf.common.ids import character_id as make_character_id
from acf.common.schema import dump, validate
from acf.common.store import next_rev, write_manifest, write_once_json
from acf.contracts.plan import PERSONALITY_FIELDS, CharacterPlan
from acf.contracts.planning import CharacterPlanV2
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record


def _fill_user_evidence(obj: dict[str, Any]) -> dict[str, Any]:
    ev = dict(obj.get("evidence") or {})
    for f in ("name", "age", "job", *PERSONALITY_FIELDS, "chapters"):
        if not ev.get(f):
            ev[f] = [{"kind": "USER", "ref": "manual-plan", "quote": ""}]
    obj["evidence"] = ev
    return obj


def import_plan(
    ctx: Context, slug: str, source: Path, brief_id: str | None = None
) -> CharacterPlan:
    raw = json.loads(Path(source).read_text("utf-8"))
    cid = raw.get("characterId") or make_character_id(slug)
    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s3-plan", "pr")
    raw = dict(raw)
    raw.setdefault("schemaVersion", "character-plan-v1")
    raw["characterId"] = cid
    raw["planRev"] = rev
    if brief_id:
        raw["briefId"] = brief_id
    raw = _fill_user_evidence(raw)
    plan: CharacterPlan = validate("character-plan-v1", raw)  # type: ignore[assignment]

    rev_dir = char_dir / "s3-plan" / rev
    write_once_json(rev_dir / "plan.json", dump(plan))
    (rev_dir / "source.json").write_text(
        json.dumps(json.loads(Path(source).read_text("utf-8")), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_manifest(rev_dir)

    state = ctx.state(cid)
    state.transition("s3", "RUNNING")
    state.transition("s3", "AWAITING_HUMAN", rev=rev)
    write_gate_record(
        char_dir,
        state,
        gate="G3",
        rev=rev,
        stage_id="s3",
        shown=[rev_dir / "plan.json"],
        decision="APPROVE",
        reviewer="user",
        reasons="manual-plan: 사용자가 직접 작성한 기획서를 들여왔다(D-0013)",
    )
    return plan


def load_approved_plan(ctx: Context, cid: str) -> tuple[CharacterPlan | CharacterPlanV2, Path]:
    """G3에서 승인한 기획서. 브리프 초안·import는 v1, 씨앗 → 변형 흐름(D-0033)은 v2다."""
    state = ctx.state(cid)
    g = state.gate("G3")
    if g.status != "APPROVED" or not g.rev:
        raise ValueError(f"{cid}: G3가 승인되지 않았다")
    p = ctx.character_dir(cid) / "s3-plan" / g.rev / "plan.json"
    if not p.exists():
        raise ValueError(f"{cid}: G3가 기획서를 고정하지 않았다({g.rev}/plan.json 없음)")
    raw = json.loads(p.read_text("utf-8"))
    contract = (
        "character-plan-v2"
        if raw.get("schemaVersion") == "character-plan-v2"
        else "character-plan-v1"
    )
    plan = validate(contract, raw)
    return plan, p  # type: ignore[return-value]


def load_approved_plan_v2(ctx: Context, cid: str) -> tuple[CharacterPlanV2, Path]:
    """새 흐름(S4a 이후)이 쓰는 v2 기획서. v1이면 이유와 함께 거절한다."""
    from acf.common.errors import CheckFailed

    plan, p = load_approved_plan(ctx, cid)
    if not isinstance(plan, CharacterPlanV2):
        raise CheckFailed(
            "s3",
            [
                "배경·자세 흐름(D-0033)은 character-plan-v2가 필요하다. "
                "acf plan seed → acf plan variants로 기획을 다시 고정한다"
            ],
        )
    return plan, p
