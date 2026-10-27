"""S3 기획 초안 (Planner 에이전트). 브리프와 프리셋 카탈로그로 기획서를 쓰고 G3 대기로 둔다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acf.common.budget import CallPlan
from acf.common.ids import character_id as make_character_id
from acf.common.schema import dump
from acf.common.store import next_rev, write_manifest, write_once_json
from acf.pipeline.agent import AgentSpec, run_agent
from acf.pipeline.context import Context
from acf.stages.s3_plan.check import check_plan_draft


def condense_presets(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for p in catalog.get("presets", []):
        out.append(
            {
                "preset_id": p.get("preset_id"),
                "name": p.get("name"),
                "summary": p.get("summary"),
                "stance": p.get("stance"),
                "expression_focus": [
                    {"role": e.get("role"), "behavior": e.get("behavior")}
                    for e in p.get("expression_focus", [])
                ],
                "values": (p.get("values") or {}).get("names", []),
                "speech": {k: (p.get("speech") or {}).get(k) for k in ("primary", "secondary")},
                "utterance_examples": p.get("utterance_examples", []),
            }
        )
    return out


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


def plan_calls(retries: int) -> list[CallPlan]:
    return [CallPlan("s3", f"Planner 기획서 초안 (재시도 포함 최대 {1 + retries}회)", 1 + retries)]


def appearance_input(ctx: Context, cid: str) -> dict[str, Any] | None:
    """S2가 외모를 고정했으면 Planner에 줄 외모 요약(D-0024, D-0042).

    이미지·이름 없이 설명과 범위만 준다.
    """
    if ctx.state(cid).stage("s2").status != "APPROVED":
        return None
    from acf.stages.s2_hero.approve import load_appearance_spec

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


def _example(cid: str, rev: str, appearance_rev: str | None = None) -> dict[str, Any]:
    lighting = "<장면의 빛 한 줄>" if appearance_rev else ""
    composition = "<인물의 자세·구도 한 줄>" if appearance_rev else ""
    return {
        "schemaVersion": "character-plan-v1",
        "characterId": cid,
        "planRev": rev,
        "briefId": None,
        "name": "<이름>",
        "age": 25,
        "job": "<직업>",
        "coreTraits": ["<행동 문장>", "<행동 문장>"],
        "contrastTrait": "<행동 문장>",
        "chapters": [
            {
                "chapterId": ch,
                "scene": "<장소·시간 한 줄>",
                "relationStage": stage,
                "lighting": lighting,
                "composition": composition,
            }
            for ch, stage in (("ch1", "지인"), ("ch2", "호감"), ("ch3", "강한 호감"))
        ],
        "evidence": {
            "name": [{"kind": "USER", "ref": "planner", "quote": ""}],
            "age": [{"kind": "USER", "ref": "planner", "quote": ""}],
            "job": [{"kind": "USER", "ref": "planner", "quote": ""}],
            "coreTraits": [{"kind": "PRESET", "ref": "STANFORD:P00:3.0", "quote": "<카드 원문>"}],
            "contrastTrait": [
                {"kind": "PRESET", "ref": "STANFORD:P00:3.0", "quote": "<카드 원문>"}
            ],
            "chapters": [{"kind": "BRIEF", "ref": "brief.md", "quote": "<브리프 원문>"}],
        },
        "appearanceRev": appearance_rev,
        "notes": "<프리셋 선택 이유와 창작 설정 설명>",
    }


def run_s3_draft(ctx: Context, cid: str, brief_text: str) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    retries = int(ctx.config.stage("s3").get("max_check_retries", 3))
    budget = ctx.budget()
    budget.check_plan(plan_calls(retries))
    rev = next_rev(char_dir / "s3-plan", "pr")
    rev_dir = char_dir / "s3-plan" / rev
    (char_dir).mkdir(parents=True, exist_ok=True)
    state.transition("s3", "RUNNING", rev=rev)
    catalog = load_catalog(ctx)
    appearance = appearance_input(ctx, cid)
    appearance_rev = appearance["appearanceRev"] if appearance else None
    spec = AgentSpec(
        role="planner", output_contract="character-plan-v1", stage="s3", max_check_retries=retries
    )
    inputs: dict[str, Any] = {
        "brief.md": brief_text,
        "presets-catalog": condense_presets(catalog),
        "ids": {"characterId": cid, "planRev": rev},
    }
    if appearance:
        inputs["appearance"] = appearance
    result = run_agent(
        spec,
        rev_dir / "workspace",
        inputs,
        [check_plan_draft(brief_text, appearance_rev)],
        ctx.text_model(cid, budget),
        ref=f"{cid}/{rev}",
        contract_example=_example(cid, rev, appearance_rev),
        backend=ctx.agent_backend(cid, budget, "s3"),
    )
    if not result.ok:
        state.transition("s3", "CHECK_FAILED", rev=rev, error="; ".join(result.problems))
        raise SystemExit(
            f"S3 자동 검사 실패({result.attempts}회):\n- " + "\n- ".join(result.problems)
        )
    plan = result.output
    if plan.characterId != cid or plan.planRev != rev:
        plan = plan.model_copy(update={"characterId": cid, "planRev": rev})
    write_once_json(rev_dir / "plan.json", dump(plan))
    (rev_dir / "brief.md").write_text(brief_text, encoding="utf-8")
    write_manifest(rev_dir)
    state.transition("s3", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G3", "AWAITING_HUMAN", rev, None)
    return rev_dir


def new_character(ctx: Context, slug: str) -> str:
    cid = make_character_id(slug)
    ctx.character_dir(cid).mkdir(parents=True, exist_ok=True)
    ctx.state(cid).save()
    return cid
