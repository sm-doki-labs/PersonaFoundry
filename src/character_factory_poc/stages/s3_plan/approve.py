"""G3가 고른 기획 v2와 선택·편집 기록을 같은 revision에 고정한다."""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_manifest, write_once_json
from character_factory_poc.contracts.planning import EDITABLE_FIELDS, PlanVariants
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import now_iso, write_gate_record
from character_factory_poc.stages.s3_plan.check_v2 import check_plan_v2


def approve_g3_variants(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G3")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G3가 대기 상태가 아니다({gate.status})")
    char_dir = ctx.character_dir(cid)
    folder = char_dir / "s3-plan" / gate.rev
    if read_json(folder / "variants.json").get("schemaVersion") == "plan-variants-v2":
        from character_factory_poc.stages.s3_plan.choice_flow import approve_choice_variants

        return approve_choice_variants(ctx, cid, answer)
    variants: PlanVariants = validate("plan-variants-v1", read_json(folder / "variants.json"))
    decision = answer.get("decision")
    ids = [p.variantId for p in variants.candidates]
    selections = answer.get("selections") or []
    if decision == "APPROVE":
        selections = [ids[0]]
    elif decision == "SELECT":
        if not isinstance(selections, list) or len(selections) != 1 or selections[0] not in ids:
            raise FactoryError(
                f"G3 SELECT는 후보 하나를 selections에 담아야 한다({', '.join(ids)})"
            )
    elif decision in {"REQUEST_CHANGES", "REJECT"}:
        selections = []
    else:
        raise FactoryError("G3 결정은 SELECT·APPROVE·REQUEST_CHANGES·REJECT 중 하나다")

    plan = selection = None
    if selections:
        edits = answer.get("edits", {})
        if not isinstance(edits, dict):
            raise FactoryError("G3 edits는 JSON 객체여야 한다")
        unknown = set(edits) - set(EDITABLE_FIELDS)
        if unknown:
            raise FactoryError(f"G3에서 수정할 수 없는 칸: {', '.join(sorted(unknown))}")
        chosen = next(p for p in variants.candidates if p.variantId == selections[0])
        raw = dump(chosen)
        raw.update(edits)
        for field, value in edits.items():
            raw["evidence"][field] = [
                {
                    "kind": "USER",
                    "ref": f"G3/{gate.rev}",
                    "quote": json.dumps(value, ensure_ascii=False),
                }
            ]
        plan = validate("character-plan-v2", raw)
        guard = read_json(folder / "workspace/inputs/name-guard.json")
        problems = check_plan_v2(None, guard)(plan)
        if problems:
            raise CheckFailed("s3", problems)
        selection = validate(
            "plan-selection-v1",
            {
                "planRev": gate.rev,
                "selected": selections[0],
                "editedFields": sorted(edits),
            },
        )

    # 답 형식도 파일을 쓰기 전에 검증해 잘못된 답이 기획서만 남기지 않게 한다.
    record = validate(
        "gate-record-v1",
        {
            "subjectId": cid,
            "gate": "G3",
            "rev": gate.rev,
            "shownArtifacts": [],
            "decision": decision,
            "reviewer": answer.get("reviewer"),
            "reasons": answer.get("reasons", ""),
            "selections": selections,
            "minutes": answer.get("minutes", 0),
            "requestedChanges": answer.get("requestedChanges") or [],
            "decidedAt": now_iso(),
        },
    )
    if plan is not None:
        write_once_json(folder / "plan.json", dump(plan))
        write_once_json(folder / "selection.json", dump(selection))
        write_manifest(folder)
    rec = write_gate_record(
        char_dir,
        state,
        gate="G3",
        rev=gate.rev,
        stage_id="s3",
        shown=[folder / "variants.json", folder / "gate-G3.html"],
        decision=record.decision,
        reviewer=record.reviewer,
        reasons=record.reasons,
        selections=selections,
        minutes=record.minutes,
        requested_changes=[dump(c) for c in record.requestedChanges],
    )
    ctx.ledger(cid).record_human(gate="G3", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    return folder
