"""cfp plan import (D-0013·D-0080, LLD §4·§8.3). 사용자 기획서를 신형 v2로 고정한다.

- v2 기획서는 검증해 씨앗과 함께 고정하고 G3 승인으로 기록한다(직접 쓴 기획서, D-0013).
- 구형 v1 기획서는 원문을 보존한 채 기획 정리(plan_normalizer)로 v2 후보 u1을 만들고 G3를 기다린다.
  빈 칸을 모델이 채우므로 사람이 승인해야 하며, 모델 호출이라 `--execute`가 필요하다.
- 승인본 읽기(load_approved_plan)는 과거 기록 때문에 v1도 계속 읽는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import NeedsInputError
from character_factory_poc.common.ids import character_id as make_character_id
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.plan import CharacterPlan
from character_factory_poc.contracts.planning import EDITABLE_FIELDS, CharacterPlanV2
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record

V1_FIELDS = ("name", "age", "job", "coreTraits", "contrastTrait", "chapters")


def plan_version(raw: dict[str, Any]) -> str:
    version = raw.get("schemaVersion")
    if version in {"character-plan-v1", "character-plan-v2"}:
        return version
    if version is not None:
        raise ValueError(f"들여올 수 없는 기획서 형식이다: {version}")
    return "character-plan-v2" if "chapterArc" in raw else "character-plan-v1"


def _seed_fields(raw: dict[str, Any], note: str) -> dict[str, Any]:
    traits = [t for t in raw.get("coreTraits") or [] if isinstance(t, str) and t.strip()]
    personality = traits[0] if traits else str(raw.get("contrastTrait") or raw.get("name") or "")
    fields: dict[str, Any] = {
        "personality": personality.strip()[:300] or "직접 작성한 기획서",
        "notes": note,
    }
    for key in ("job", "age", "gender", "background"):
        if raw.get(key) not in (None, ""):
            fields[key] = raw[key]
    return fields


def _character(ctx: Context, slug: str, raw: dict[str, Any]) -> str:
    cid = raw.get("characterId") or make_character_id(slug)
    ctx.character_dir(cid).mkdir(parents=True, exist_ok=True)
    state = ctx.state(cid)
    if not state.path.exists():
        state.save()
    return cid


def import_plan(
    ctx: Context, slug: str, source: Path, brief_id: str | None = None
) -> dict[str, Any]:
    """기획서 파일을 신형으로 고정한다. 돌려주는 값: characterId·planRev·mode·path."""
    from character_factory_poc.stages.s3_plan.seed import write_seed

    text = Path(source).read_text("utf-8")
    raw = dict(json.loads(text))
    version = plan_version(raw)
    note = "cfp plan import로 들여온 사용자 기획서" + (f" (brief {brief_id})" if brief_id else "")
    if version == "character-plan-v1":
        return _upgrade_v1(ctx, slug, raw, note)
    cid = _character(ctx, slug, raw)
    seed = write_seed(ctx, cid, _seed_fields(raw, note))
    from character_factory_poc.stages.s3_plan.common import appearance_input

    appearance = appearance_input(ctx, cid)
    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s3-plan", "pr")
    raw.update(
        schemaVersion="character-plan-v2",
        characterId=cid,
        planRev=rev,
        seedRev=seed.seedRev,
        variantId="u1",
        appearanceRev=appearance["appearanceRev"] if appearance else None,
    )
    evidence = dict(raw.get("evidence") or {})
    for field in (*EDITABLE_FIELDS, "chapterArc"):
        if not evidence.get(field):
            evidence[field] = [{"kind": "USER", "ref": "manual-plan", "quote": ""}]
    raw["evidence"] = evidence
    plan: CharacterPlanV2 = validate("character-plan-v2", raw)  # type: ignore[assignment]
    rev_dir = char_dir / "s3-plan" / rev
    write_once_json(rev_dir / "plan.json", dump(plan))
    (rev_dir / "source.json").write_text(text, encoding="utf-8")
    write_manifest(rev_dir)
    state = ctx.state(cid)
    state.transition("s3", "RUNNING", rev=rev)
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
        reasons="manual-plan: 사용자가 직접 작성한 v2 기획서를 들여왔다(D-0013)",
    )
    return {"characterId": cid, "planRev": rev, "mode": "approved", "path": rev_dir}


def _upgrade_v1(ctx: Context, slug: str, raw: dict[str, Any], note: str) -> dict[str, Any]:
    """구형 기획서는 형식을 확인한 뒤 원문을 근거로 기획 정리에 넘겨 v2 후보를 만든다."""
    from character_factory_poc.stages.s3_plan.own import run_s3_own
    from character_factory_poc.stages.s3_plan.seed import write_seed

    probe = dict(raw, schemaVersion="character-plan-v1", characterId="cf-00000000-probe")
    probe.setdefault("planRev", "pr1")
    probe.setdefault("evidence", {f: [{"kind": "USER", "ref": "manual-plan"}] for f in V1_FIELDS})
    validate("character-plan-v1", probe)
    if not ctx.execute:
        raise NeedsInputError(
            "구형 기획서(character-plan-v1)는 기획 정리 모델로 신형으로 올린다. "
            "--execute로 다시 실행하면 u1 후보를 만들고 G3를 기다린다"
        )
    cid = _character(ctx, slug, raw)
    write_seed(ctx, cid, _seed_fields(raw, note + " · 구형 v1에서 올림"))
    original = {k: v for k, v in raw.items() if k not in {"characterId", "planRev", "evidence"}}
    user_text = (
        "사용자가 쓴 구형 기획서(character-plan-v1) 원문이다. 내용을 보존해 v2로 정리한다.\n\n"
    )
    user_text += json.dumps(original, ensure_ascii=False, indent=2)
    rev_dir = run_s3_own(ctx, cid, user_text)
    return {"characterId": cid, "planRev": rev_dir.name, "mode": "upgraded", "path": rev_dir}


def load_approved_plan(ctx: Context, cid: str) -> tuple[CharacterPlan | CharacterPlanV2, Path]:
    """G3에서 승인한 기획서. 신규는 모두 v2(D-0080)이고, 과거 기록의 v1도 읽는다."""
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
    from character_factory_poc.common.errors import CheckFailed

    plan, p = load_approved_plan(ctx, cid)
    if not isinstance(plan, CharacterPlanV2):
        raise CheckFailed(
            "s3",
            [
                "배경·자세 흐름(D-0033)은 character-plan-v2가 필요하다. "
                "cfp plan seed → cfp plan variants로 기획을 다시 고정한다"
            ],
        )
    return plan, p
