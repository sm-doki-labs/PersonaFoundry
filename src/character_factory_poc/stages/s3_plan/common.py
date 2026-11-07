"""S3 공용 도우미: 새 캐릭터 만들기, 승인 외모 요약, Stanford 프리셋 카드(D-0080 정리).

구형 브리프 초안(character-plan-v1, Planner)은 D-0080으로 씨앗 → 변형 경로에 통합되어 지웠다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.ids import character_id as make_character_id
from character_factory_poc.common.schema import dump
from character_factory_poc.pipeline.context import Context


def new_character(ctx: Context, slug: str) -> str:
    cid = make_character_id(slug)
    ctx.character_dir(cid).mkdir(parents=True, exist_ok=True)
    ctx.state(cid).save()
    return cid


def appearance_input(ctx: Context, cid: str) -> dict[str, Any] | None:
    """S2가 외모를 고정했으면 기획 저작에 줄 외모 요약(D-0024, D-0042).

    이미지·이름 없이 설명과 범위만 준다.
    """
    if ctx.state(cid).stage("s2").status != "APPROVED":
        return None
    from character_factory_poc.stages.s2_hero.approve import load_appearance_spec

    spec, _ = load_appearance_spec(ctx, cid)
    return {
        "appearanceRev": spec.appearanceRev,
        "descriptionKo": spec.descriptionKo,
        "scope": dump(spec.scope),
        "use": (
            "외형 묘사와 챕터 장면의 조명·구도에만 쓴다. "
            "성격·말투·직업의 근거로 쓰지 않는다(D-0005)."
        ),
    }


def full_preset_card(catalog: dict[str, Any], preset_id: str) -> dict[str, Any] | None:
    for p in catalog.get("presets", []):
        if p.get("preset_id") == preset_id:
            drop = {
                "personality_data",
                "core_system_prompt",
                "core_sha256",
                "interview_editorial_links",
                "bfi2_facet_scores",
            }
            card = {k: v for k, v in p.items() if k not in drop}
            card["schema_version"] = catalog.get("schema_version")
            return card
    return None


def load_catalog(ctx: Context) -> dict[str, Any]:
    path = ctx.config.resources.get("stanford_presets_json")
    if not path:
        raise ValueError("factory.toml [resources] stanford_presets_json 이 필요하다")
    return json.loads(Path(path).read_text("utf-8"))
