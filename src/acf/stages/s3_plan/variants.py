"""씨앗 하나를 상세 기획 변형으로 확장하고 G3 선택을 기다린다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from acf.common.budget import CallPlan
from acf.common.canonical import sha256_file
from acf.common.errors import (
    AgentFormatError,
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
    NeedsInputError,
)
from acf.common.schema import dump, validate
from acf.common.store import next_rev, read_json, write_manifest, write_once_json, write_once_text
from acf.contracts.planning import (
    CHAPTER_SLOTS,
    EDITABLE_FIELDS,
    CharacterPlanV2,
    PlanSeed,
    PlanVariants,
    ProfileCard,
)
from acf.pipeline.agent import AgentSpec, run_agent
from acf.pipeline.context import Context
from acf.stages.s1_reference.ranking import all_names, load_ranking
from acf.stages.s2_hero.approve import load_appearance_spec
from acf.stages.s3_plan.check_v2 import check_variants, name_guard
from acf.stages.s3_plan.check_v2 import codex_checks as codex_checks
from acf.stages.s3_plan.draft import appearance_input
from acf.stages.s3_plan.page import render_g3_page
from acf.stages.s3_plan.seed import load_latest_seed


def _config(ctx: Context) -> dict[str, int]:
    cfg = ctx.config.stage("s3")
    count = int(cfg.get("variants", 3))
    retries = int(cfg.get("max_check_retries", 3))
    if not 1 <= count <= 5 or retries < 0:
        raise FactoryError("[stages.s3] variants는 1~5, max_check_retries는 0 이상이어야 한다")
    return {"variants": count, "max_check_retries": retries}


def plan_calls(ctx: Context) -> list[CallPlan]:
    """형식 재시도 2회와 검사 재시도까지 합친 호출 상한이다."""
    count = 3 + _config(ctx)["max_check_retries"]
    return [CallPlan("s3-variants", "Planner 상세 기획 변형(형식·검사 재시도 포함)", count)]


def _preflight(ctx: Context, cid: str) -> tuple[PlanSeed, dict, list[dict]]:
    if ctx.state(cid).gate("G2").status != "APPROVED":
        raise GateNotApprovedError(f"{cid}: 상세 기획에는 G2 승인이 필요하다")
    seed = load_latest_seed(ctx, cid)
    if seed is None:
        raise NeedsInputError(
            f"{cid}: 기획 씨앗이 없다. 'acf plan seed'로 성격·직업·나이·성별·배경을 먼저 쓴다"
        )
    if ctx.state(cid).stage("s3").status == "AWAITING_HUMAN":
        raise FactoryError(
            f"{cid}: G3 검토 대기 중이다. 기존 안에 REQUEST_CHANGES 또는 REJECT를 기록한 뒤 "
            "새 revision을 만든다"
        )
    spec, _ = load_appearance_spec(ctx, cid)
    path = ctx.character_dir(cid) / "s1-reference" / spec.sourceReferenceRev / "ranking.json"
    names = all_names(load_ranking(read_json(path))) if path.exists() else []
    return seed, appearance_input(ctx, cid), name_guard(names)


def _inputs(seed: PlanSeed, appearance: dict, guard: list[dict], rev: str) -> dict[str, Any]:
    return {
        "seed": dump(seed),
        "appearance": appearance,
        "chapter-slots": CHAPTER_SLOTS,
        "profile-card-fields": list(ProfileCard.model_fields),
        "name-guard": guard,
        "ids": {
            "characterId": seed.characterId,
            "planRev": rev,
            "seedRev": seed.seedRev,
            "appearanceRev": appearance["appearanceRev"],
        },
    }


def _example(seed: PlanSeed, appearance: dict, rev: str) -> dict:
    return {
        "schemaVersion": "character-plan-v2",
        "characterId": seed.characterId,
        "planRev": rev,
        "seedRev": seed.seedRev,
        "variantId": "v1",
        "appearanceRev": appearance["appearanceRev"],
        "name": "<허구 이름>",
        "age": seed.age or 25,
        "gender": seed.gender or "other",
        "job": seed.job or "<현실의 직업>",
        "tagline": "<이 캐릭터를 소개하는 한 줄>",
        "background": seed.background or "<짧고 구체적인 현대 한국 배경>",
        "coreTraits": ["상대가 망설이면 먼저 선택지를 좁혀 제안한다"],
        "contrastTrait": "거절을 들으면 이유를 캐묻지 않고 멈춘다",
        "choices": [
            {"situation": s, "firstMove": "<이 변형이 먼저 선택하는 구체적 행동>"}
            for s in ("상대가 약속에 늦을 때", "칭찬을 들었을 때", "관계 확답을 재촉받을 때")
        ],
        "lifeAndTastes": ["<일상의 습관>", "<좋아하는 취미>", "<생활의 작은 취향>"],
        "wantsAndFears": ["<원하는 관심과 피하고 싶은 관계>"],
        "misreadings": ["<행동이 오해받는 지점>"],
        "voiceSummary": "<구별되는 어미·호흡·반응 순서>",
        "voiceExamples": ["<실제 대사 1>", "<실제 대사 2>"],
        "boundaries": ["<하지 않는 행동과 한계>"],
        "profileCard": dump(ProfileCard()),
        "chapterArc": [
            {
                "chapterId": ch,
                "slot": s["slot"],
                "title": s["title"],
                "entryStage": s["entry"],
                "targetStage": s["target"],
                "arc": "<장소 없이 관계가 어떻게 움직이는지 한 줄>",
            }
            for ch, s in CHAPTER_SLOTS.items()
        ],
        "evidence": {
            "coreTraits": [{"kind": "SEED", "ref": seed.seedRev, "quote": seed.personality}]
        },
        "notes": "",
    }


def _fix_plan(
    plan: CharacterPlanV2,
    seed: PlanSeed,
    appearance: dict,
    rev: str,
    variant: str,
    own: bool = False,
) -> CharacterPlanV2:
    raw = dump(plan)
    raw.update(
        characterId=seed.characterId,
        planRev=rev,
        seedRev=seed.seedRev,
        variantId=variant,
        appearanceRev=appearance["appearanceRev"],
    )
    arcs = {arc["chapterId"]: arc["arc"] for arc in raw["chapterArc"]}
    raw["chapterArc"] = [
        {
            "chapterId": ch,
            "slot": s["slot"],
            "title": s["title"],
            "entryStage": s["entry"],
            "targetStage": s["target"],
            "arc": arcs[ch],
        }
        for ch, s in CHAPTER_SLOTS.items()
    ]
    if own:
        for field in (*EDITABLE_FIELDS, "chapterArc"):
            if not raw["evidence"].get(field):
                raw["evidence"][field] = [{"kind": "AGENT", "ref": "plan_normalizer", "quote": ""}]
    return validate("character-plan-v2", raw)  # type: ignore[return-value]


def _publish(
    ctx: Context,
    cid: str,
    rev_dir: Path,
    seed: PlanSeed,
    plans: list[CharacterPlanV2],
    mode: str,
    axis_note: str = "",
) -> Path:
    seed_path = rev_dir.parent / "seeds" / f"{seed.seedRev}.json"
    variants: PlanVariants = validate(
        "plan-variants-v1",
        {
            "characterId": cid,
            "planRev": rev_dir.name,
            "seedRev": seed.seedRev,
            "seedSha256": sha256_file(seed_path),
            "mode": mode,
            "axisNote": axis_note,
            "candidates": [dump(p) for p in plans],
        },
    )  # type: ignore[assignment]
    write_once_json(rev_dir / "variants.json", dump(variants))
    write_once_text(rev_dir / "gate-G3.html", render_g3_page(variants=variants))
    write_manifest(rev_dir)
    state = ctx.state(cid)
    state.transition("s3", "AWAITING_HUMAN", rev=rev_dir.name)
    state.set_gate("G3", "AWAITING_HUMAN", rev_dir.name, None)
    return rev_dir


def run_s3_variants(ctx: Context, cid: str) -> Path:
    seed, appearance, guard = _preflight(ctx, cid)
    cfg = _config(ctx)
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx))
    rev = next_rev(ctx.character_dir(cid) / "s3-plan", "pr")
    rev_dir = ctx.character_dir(cid) / "s3-plan" / rev
    ctx.state(cid).transition("s3", "RUNNING", rev=rev)
    try:
        inputs = _inputs(seed, appearance, guard, rev)
        inputs["variant-count"] = cfg["variants"]
        example = _example(seed, appearance, rev)
        result = run_agent(
            AgentSpec(
                role="plan_variants",
                output_contract="plan-variants-output-v1",
                stage="s3-variants",
                max_check_retries=cfg["max_check_retries"],
            ),
            rev_dir / "workspace",
            inputs,
            [check_variants(seed, cfg["variants"], guard)],
            ctx.text_model(cid, budget),
            ref=f"{cid}/{rev}",
            contract_example={
                "variants": [example | {"variantId": f"v{i + 1}"} for i in range(cfg["variants"])],
                "axisNote": "",
            },
            backend=ctx.agent_backend(cid, budget, "s3-variants"),
        )
        if not result.ok:
            raise CheckFailed("s3", result.problems)
        plans = [
            _fix_plan(p, seed, appearance, rev, f"v{i}")
            for i, p in enumerate(result.output.variants, 1)
        ]
        return _publish(ctx, cid, rev_dir, seed, plans, "variants", result.output.axisNote)
    except (CheckFailed, AgentFormatError) as exc:
        ctx.state(cid).transition("s3", "CHECK_FAILED", rev=rev, error=str(exc))
        if isinstance(exc, AgentFormatError):
            raise CheckFailed("s3", [str(exc)]) from exc
        raise
