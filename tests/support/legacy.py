"""과거 기록(character-plan-v1)을 읽는 단계의 시험용 도우미(D-0080).

신규 기획은 모두 v2지만 S3r·S4 프레임·S7·S9 등은 과거 v1 승인본을 계속 읽는다. 그 읽기 경로를
시험하려고 예전 `cfp plan import`와 같은 방식으로 v1 기획서를 G3 승인 상태로 깐다. 제품 코드에서는
v1을 새로 쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.ids import character_id as make_character_id
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.plan import PERSONALITY_FIELDS, CharacterPlan
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record


def _fill_user_evidence(obj: dict[str, Any]) -> dict[str, Any]:
    ev = dict(obj.get("evidence") or {})
    for f in ("name", "age", "job", *PERSONALITY_FIELDS, "chapters"):
        if not ev.get(f):
            ev[f] = [{"kind": "USER", "ref": "manual-plan", "quote": ""}]
    obj["evidence"] = ev
    return obj


def approve_v1_plan(ctx: Context, cid: str, raw: dict[str, Any]) -> CharacterPlan:
    """있는 캐릭터에 v1 기획서를 G3 승인 상태로 고정한다(과거 기록 재현)."""
    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s3-plan", "pr")
    raw = _fill_user_evidence(
        dict(raw, schemaVersion="character-plan-v1", characterId=cid, planRev=rev)
    )
    plan: CharacterPlan = validate("character-plan-v1", raw)  # type: ignore[assignment]
    rev_dir = char_dir / "s3-plan" / rev
    write_once_json(rev_dir / "plan.json", dump(plan))
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
        reasons="시험용 과거 v1 기획서",
    )
    return plan


def import_plan(
    ctx: Context, slug: str, source: Path, brief_id: str | None = None
) -> CharacterPlan:
    """예전 v1 `cfp plan import`와 같은 결과를 만든다(시험 전용)."""
    raw = json.loads(Path(source).read_text("utf-8"))
    cid = raw.get("characterId") or make_character_id(slug)
    ctx.character_dir(cid).mkdir(parents=True, exist_ok=True)
    if brief_id:
        raw["briefId"] = brief_id
    return approve_v1_plan(ctx, cid, raw)
