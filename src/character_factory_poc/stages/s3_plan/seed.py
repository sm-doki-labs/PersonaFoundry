"""사람이 쓴 기획 씨앗을 단조 증가하는 sd revision으로 고정한다."""

from __future__ import annotations

import re

from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, read_json, write_once_json
from character_factory_poc.contracts.planning import PlanSeed
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.draft import appearance_input


def _seed_paths(ctx: Context, cid: str):
    folder = ctx.character_dir(cid) / "s3-plan" / "seeds"
    return sorted(
        (p for p in folder.glob("sd*.json") if re.fullmatch(r"sd\d+", p.stem)),
        key=lambda p: int(p.stem[2:]),
    )


def write_seed(ctx: Context, cid: str, fields: dict) -> PlanSeed:
    """비운 성별은 승인 외모 범위에서 채우고 기존 씨앗은 보존한다."""
    folder = ctx.character_dir(cid) / "s3-plan" / "seeds"
    paths = _seed_paths(ctx, cid)
    # next_rev는 폴더 이름만 인식하므로 .json 씨앗 번호도 함께 비교한다.
    number = max(int(next_rev(folder, "sd")[2:]), int(paths[-1].stem[2:]) + 1 if paths else 1)
    raw = dict(fields)
    raw.update(characterId=cid, seedRev=f"sd{number}")
    if not raw.get("gender"):
        appearance = appearance_input(ctx, cid)
        gender = (appearance or {}).get("scope", {}).get("characterGender")
        if gender in {"female", "male"}:
            raw["gender"] = gender
    seed: PlanSeed = validate("plan-seed-v1", raw)  # type: ignore[assignment]
    write_once_json(folder / f"{seed.seedRev}.json", dump(seed))
    return seed


def load_latest_seed(ctx: Context, cid: str) -> PlanSeed | None:
    """번호가 가장 큰 씨앗을 읽는다. 아직 쓰지 않았으면 None이다."""
    paths = _seed_paths(ctx, cid)
    if not paths:
        return None
    return validate("plan-seed-v1", read_json(paths[-1]))  # type: ignore[return-value]
