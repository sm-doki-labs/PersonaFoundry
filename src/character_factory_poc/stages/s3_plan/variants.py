"""씨앗 하나를 상세 기획 변형으로 확장하고 G3 선택을 기다린다."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import (
    AgentFormatError,
    CheckFailed,
    FactoryError,
    NeedsInputError,
)
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.planning import (
    CHAPTER_SLOTS,
    EDITABLE_FIELDS,
    CharacterPlanV2,
    PlanSeed,
    PlanVariants,
    ProfileCard,
)
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s3_plan.check_v2 import check_variants, name_guard
from character_factory_poc.stages.s3_plan.check_v2 import codex_checks as codex_checks
from character_factory_poc.stages.s3_plan.common import appearance_input
from character_factory_poc.stages.s3_plan.page import render_g3_page
from character_factory_poc.stages.s3_plan.seed import load_latest_seed


def _config(ctx: Context) -> dict[str, int]:
    cfg = ctx.config.stage("s3")
    count = int(cfg.get("variants", 3))
    retries = int(cfg.get("max_check_retries", 3))
    if not 1 <= count <= 5 or retries < 0:
        raise FactoryError("[stages.s3] variants는 1~5, max_check_retries는 0 이상이어야 한다")
    return {"variants": count, "max_check_retries": retries}


def plan_calls(ctx: Context) -> list[CallPlan]:
    """형식 재시도 2회와 검사 재시도까지 합친 호출 상한이다."""
    if ctx.config.stage("s7").get("formation_profile") == "ko-text-choice-voice-long-v2":
        return [CallPlan("s3-choices", "요구·후보·의미 검토(형식 재시도 포함)", 9)]
    if ctx.text_deck_enabled:
        return [
            CallPlan(
                "s3",
                "Sol 제약·Gemini 초안·Gemini 말투(형식 재시도·검사 재시도 1회 포함, D-0086)",
                12 + min(1, _config(ctx)["max_check_retries"]),
                est_cost_usd=None,
            )
        ]
    count = 3 + _config(ctx)["max_check_retries"]
    return [CallPlan("s3-variants", "Planner 상세 기획 변형(형식·검사 재시도 포함)", count)]


def _preflight(ctx: Context, cid: str) -> tuple[PlanSeed, dict, list[dict]]:
    # D-0042: 외모 명세는 G2가 아니라 s2 승인이 기준이다. D-0080: 페르소나 우선 캐릭터는
    # 외모 없이(appearance=None) 같은 변형 경로를 쓴다.
    seed = load_latest_seed(ctx, cid)
    if seed is None:
        raise NeedsInputError(
            f"{cid}: 기획 씨앗이 없다. 'cfp plan seed'로 성격·직업·나이·성별·배경을 먼저 쓴다"
        )
    if ctx.state(cid).stage("s3").status == "AWAITING_HUMAN":
        raise FactoryError(
            f"{cid}: G3 검토 대기 중이다. 기존 안에 REQUEST_CHANGES 또는 REJECT를 기록한 뒤 "
            "새 revision을 만든다"
        )
    state = ctx.state(cid)
    appearance_axis = state.stage("s1").status != "PENDING" or state.gate("G1").status != "PENDING"
    if appearance_axis and state.stage("s2").status != "APPROVED":
        # 외모 축을 시작한 캐릭터는 지금처럼 s2 승인 뒤에만 기획한다.
        load_appearance_spec(ctx, cid)
    appearance = appearance_input(ctx, cid)
    names: list[str] = []
    if appearance is not None:
        spec, _ = load_appearance_spec(ctx, cid)
        path = ctx.character_dir(cid) / "s1-reference" / spec.sourceReferenceRev / "ranking.json"
        names = all_names(load_ranking(read_json(path))) if path.exists() else []
    return seed, appearance, name_guard(names)


def _appearance_rev(appearance: dict | None) -> str | None:
    return appearance["appearanceRev"] if appearance else None


def _inputs(seed: PlanSeed, appearance: dict | None, guard: list[dict], rev: str) -> dict[str, Any]:
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
            "appearanceRev": _appearance_rev(appearance),
        },
    }


def _example(seed: PlanSeed, appearance: dict | None, rev: str) -> dict:
    return {
        "schemaVersion": "character-plan-v2",
        "characterId": seed.characterId,
        "planRev": rev,
        "seedRev": seed.seedRev,
        "variantId": "v1",
        "appearanceRev": _appearance_rev(appearance),
        "name": "<허구 이름>",
        "age": seed.age or 25,
        "gender": seed.gender or "other",
        "job": seed.job or "<현실의 직업>",
        "tagline": "<이 캐릭터를 소개하는 한 줄>",
        "background": seed.background or "<짧고 구체적인 현대 한국 배경>",
        # D-0089: 예시 성격 문장·상황을 두면 모든 캐릭터가 그 틀을 따른다(K-0076).
        # 자리표시자만 둔다.
        "coreTraits": ["<기본 선택과 그 이득·비용이 보이는 행동 문장>"],
        "contrastTrait": "<해석이 뒤집히는 조건과 그때의 선택>",
        "choices": [
            {"situation": s, "firstMove": "<이 변형이 먼저 고르는 관찰 가능한 행동>"}
            for s in (
                "<이 씨앗의 생활에서 생기는 근거 없는 시비 상황>",
                "<이 씨앗의 생활에서 생기는 압력 상황>",
                "<이 씨앗의 생활에서 생기는 다른 압력 상황>",
            )
        ],
        "lifeAndTastes": ["<일상의 습관>", "<좋아하는 취미>", "<생활의 작은 취향>"],
        "wantsAndFears": ["<핵심 긴장을 담은 인물의 문장>"],
        "misreadings": ["<행동이 오해받는 지점>"],
        "voiceSummary": "<상대높임 등급과 대표 종결 형태 표기, 범주별 말투 경향>",
        "voiceExamples": ["<사람 검토용 초안 1>", "<사람 검토용 초안 2>"],
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
    appearance: dict | None,
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
        appearanceRev=_appearance_rev(appearance),
        selectedTraits=[dump(t) for t in seed.selectedTraits],
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


def run_s3_from_brief(ctx: Context, cid: str, brief_text: str) -> Path:
    """D-0080: 브리프 원문을 씨앗으로 고정한 뒤(이미 있으면 그대로) 변형 경로로 기획한다."""
    from character_factory_poc.stages.s3_plan.seed import seed_fields_from_brief, write_seed

    if load_latest_seed(ctx, cid) is None:
        write_seed(ctx, cid, seed_fields_from_brief(brief_text))
    return run_s3_variants(ctx, cid)


def run_s3_variants(ctx: Context, cid: str) -> Path:
    if ctx.config.stage("s7").get("formation_profile") == "ko-text-choice-voice-long-v2":
        from character_factory_poc.stages.s3_plan.choice_flow import run_choice_variants

        return run_choice_variants(ctx, cid)
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
        if ctx.text_deck_enabled:
            from character_factory_poc.stages.s3_plan.diversity import (
                avoid_list,
                draw_anchors,
                recent_anchor_values,
            )

            # D-0100: 다양성은 바깥에서 넣는다(후보별 구체 단서 + 이미 쓴 이름·취미·음식).
            chars_dir = ctx.character_dir(cid).parent
            inputs["diversity-anchors"] = draw_anchors(
                cid, rev, cfg["variants"], exclude=recent_anchor_values(chars_dir, cid)
            )
            inputs["avoid-list"] = avoid_list(chars_dir, cid)
        if ctx.text_deck_enabled:
            from character_factory_poc.stages.s3_plan.model_deck import brief

            inputs["fixed-requirements"] = brief(ctx, cid, rev_dir, seed, budget)
        example = _example(seed, appearance, rev)
        result = run_agent(
            AgentSpec(
                role="plan_variants",
                output_contract="plan-variants-output-v1",
                stage="s3-variants",
                max_check_retries=min(1, cfg["max_check_retries"])
                if ctx.text_deck_enabled
                else cfg["max_check_retries"],
            ),
            rev_dir / "workspace",
            inputs,
            [check_variants(seed, cfg["variants"], guard)],
            ctx.role_model(cid, budget, "plan_variants"),
            ref=f"{cid}/{rev}",
            contract_example={
                "variants": [example | {"variantId": f"v{i + 1}"} for i in range(cfg["variants"])],
                "axisNote": "",
            },
            backend=ctx.agent_backend(cid, budget, "s3-variants"),
        )
        if not result.ok:
            raise CheckFailed("s3", result.problems)
        if ctx.text_deck_enabled:
            from character_factory_poc.stages.s3_plan.model_deck import finish

            final = finish(
                ctx,
                cid,
                rev_dir,
                seed,
                result.output,
                budget,
                [check_variants(seed, cfg["variants"], guard)],
            )
            result.output = final
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
