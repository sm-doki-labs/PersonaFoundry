"""S4a 배경 후보·plate 생성. API와 codex_exec가 같은 검사를 쓴다."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from character_factory_poc.common.aspect import parse_ratio, request_size
from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError, NameLeakError
from character_factory_poc.common.names import normalize_name
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.qa import QaSummary
from character_factory_poc.contracts.scene import BackgroundOutput
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ImageRequest
from character_factory_poc.stages.image_qa import (
    RUBRICS,
    ensure_judge,
    generate_checked,
    qa_settings,
    summarize,
    worst_case_calls,
)
from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s3_plan.importer import load_approved_plan_v2
from character_factory_poc.stages.s4a_backgrounds.page import render_g4a_page
from character_factory_poc.stages.s4a_backgrounds.prompt import PLATE_NEGATIVE, build_plate_prompt

DEFAULTS = {"candidates_per_chapter": 3, "plates": True, "aspect_ratio": "9:16"}
PERSON_WORD = re.compile(r"\b(woman|man|person|people|girl|boy)\b", re.I)


def config_for(ctx: Context, stage: str, defaults: dict) -> dict:
    cfg = defaults | ctx.config.stage(stage)
    if "aspect_ratio" in cfg:
        try:
            ratio = parse_ratio(str(cfg["aspect_ratio"]))
        except ValueError as e:
            raise CheckFailed(stage, [str(e)]) from e
        if ratio[0] * 16 != ratio[1] * 9:
            raise CheckFailed(stage, ["이 흐름의 aspect_ratio는 9:16이어야 한다"])
    if "candidates_per_chapter" in cfg:
        n = cfg["candidates_per_chapter"]
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise CheckFailed(stage, ["candidates_per_chapter는 1 이상의 정수다"])
    return cfg


def s4a_config(ctx: Context) -> dict:
    cfg = config_for(ctx, "s4a", DEFAULTS)
    if not isinstance(cfg["plates"], bool):
        raise CheckFailed("s4a", ["plates는 true 또는 false다"])
    return cfg


def plan_calls(ctx: Context) -> list[CallPlan]:
    cfg = s4a_config(ctx)
    plans = [CallPlan("s4a", "Location Scout 배경 후보 작성", 1)]
    if cfg["plates"]:
        n = 3 * cfg["candidates_per_chapter"]
        images, judges = worst_case_calls(qa_settings(ctx), n)
        description = f"9:16 배경 plate {n}장"
        if judges:
            description += f" (자동 검사 포함 최대 {images}장)"
        plans.append(CallPlan("s4a", description, images))
        if judges:
            plans.append(CallPlan("s4a", "배경 plate 비전 자동 검사 (최대)", judges))
    return plans


def plan_summary(plan) -> dict:
    return {
        k: dump(plan)[k]
        for k in (
            "name",
            "job",
            "background",
            "lifeAndTastes",
            "chapterArc",
        )
    }


def ranking_guard(ctx: Context, cid: str, reference_rev: str) -> list[dict]:
    path = ctx.character_dir(cid) / "s1-reference" / reference_rev / "ranking.json"
    names = all_names(load_ranking(read_json(path))) if path.exists() else []
    # 이름 원문은 다음 에이전트에게 주지 않고 길이와 해시로 검사한다(D-0017).
    return [
        {"length": len(key), "sha256": hashlib.sha256(key.encode()).hexdigest()}
        for name in names
        if len(key := normalize_name(name)) >= 2
    ]


def check_no_names(value: Any, guard: list[dict]) -> list[str]:
    if hasattr(value, "model_dump"):
        value = dump(value)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    normalized = normalize_name(text)
    for length in {g["length"] for g in guard}:
        forbidden = {g["sha256"] for g in guard if g["length"] == length}
        if any(
            hashlib.sha256(normalized[i : i + length].encode()).hexdigest() in forbidden
            for i in range(len(normalized) - length + 1)
        ):
            return ["순위 목록의 인물 이름을 쓰지 않는다(FR-35)"]
    return []


def assert_no_names(value: Any, guard: list[dict]) -> None:
    if check_no_names(value, guard):
        raise NameLeakError("입력·산출물·이미지 프롬프트에 순위 목록의 이름이 있다(FR-35)")


def empty_scene_problems(text: str) -> list[str]:
    if not text.strip():
        return ["plateBrief에 인물 없는 장면을 묘사한다"]
    for match in PERSON_WORD.finditer(text):
        if not re.search(r"\bno\s+$", text[: match.start()], re.I):
            return ["plateBrief는 빈 장면이어야 한다: 인물 단어 앞에 'no '를 쓴다"]
    return []


def check_backgrounds(count: int, guard: list[dict]):
    def check(out: BackgroundOutput) -> list[str]:
        problems = check_no_names(out, guard)
        for ch in out.chapters:
            expected = {f"{ch.chapterId}-b{i}" for i in range(1, count + 1)}
            if len(ch.candidates) != count or {c.candidateId for c in ch.candidates} != expected:
                problems.append(f"{ch.chapterId}: 후보 {count}개와 chX-b1..bN ID가 필요하다")
            places = [normalize_name(c.place) for c in ch.candidates]
            if not all(places) or len(set(places)) != len(places):
                problems.append(f"{ch.chapterId}: 챕터 안의 장소는 서로 달라야 한다")
            for candidate in ch.candidates:
                problems.extend(empty_scene_problems(candidate.plateBrief))
        return problems

    return check


def codex_checks(stage: str, workspace: Path) -> tuple[str, list]:
    if stage != "s4a":
        raise ValueError(f"지원하지 않는 검사 단계: {stage}")
    settings = read_json(workspace / "inputs" / "settings.json")
    guard = read_json(workspace / "inputs" / "name-guard.json")
    return "background-candidates-output-v1", [check_backgrounds(settings["count"], guard)]


def call_agent(ctx, cid, budget, stage, role, contract, workspace, inputs, checks, example):
    assert_no_names(inputs, inputs["name-guard"])
    result = run_agent(
        AgentSpec(role=role, output_contract=contract, stage=stage),
        workspace,
        inputs,
        checks,
        ctx.text_model(cid, budget),
        ref=f"{cid}/{workspace.parent.name}/{stage}",
        contract_example=example,
        backend=ctx.agent_backend(cid, budget, stage),
    )
    if not result.ok:
        raise CheckFailed(stage, result.problems)
    return result.output


def carry_qa(src_dir: Path, rev_dir: Path, qa: QaSummary | None) -> None:
    """요약의 상대 경로를 유지하고 보고서와 모든 시도 이미지를 바이트 그대로 이월한다."""
    if qa is None:
        return
    report = read_json(src_dir / qa.report)
    write_once_bytes(rev_dir / qa.report, (src_dir / qa.report).read_bytes())
    for attempt in report["rounds"]:
        rel = attempt["filePath"]
        write_once_bytes(rev_dir / rel, (src_dir / rel).read_bytes())


def make_plate(ctx, cid, budget, stage, rev, rev_dir, plate_id, chapter, guard, settings, warning):
    prompt = build_plate_prompt(
        chapter.plateBrief,
        chapter.place,
        chapter.timeOfDay,
        chapter.mood,
    )
    assert_no_names(prompt + PLATE_NEGATIVE, guard)
    rubric = RUBRICS["plate-v1"]
    result = generate_checked(
        image_model=ctx.image_model(cid, budget),
        vision=ctx.vision_model(cid, budget) if settings.enabled else None,
        request=ImageRequest(
            stage=stage,
            prompt=prompt,
            ref=f"{cid}/{rev}/{plate_id}",
            negative_prompt=PLATE_NEGATIVE,
            size=request_size((9, 16)),
        ),
        ratio=(9, 16),
        rubric=rubric,
        context=(
            f"Place: {chapter.place}. Time: {chapter.timeOfDay}. Mood: {chapter.mood}. "
            f"Plate brief: {chapter.plateBrief}"
        ),
        judge_refs=[],
        out_dir=rev_dir,
        image_id=plate_id,
        settings=settings,
        warning=warning,
    )
    rel = f"plates/{plate_id}.png"
    write_once_bytes(rev_dir / rel, result.data)
    qa = None
    if result.report is not None:
        report_rel = f"qa/{plate_id}.json"
        write_once_json(rev_dir / report_rel, dump(result.report))
        qa = summarize(result.report, rubric, report_rel)
    return {"id": plate_id, "path": rel, "sha256": sha256_file(rev_dir / rel)}, qa


def _example(count: int) -> dict:
    return {
        "chapters": [
            {
                "chapterId": ch,
                "candidates": [
                    {
                        "candidateId": f"{ch}-b{i}",
                        "place": f"동네 장소 {i}",
                        "timeOfDay": "저녁",
                        "why": "생활 동선과 이어진다",
                        "props": [],
                        "mood": "따뜻한 빛",
                        "sceneFactsDraft": ["창이 있다", "작은 탁자가 있다"],
                        "boundariesDraft": [],
                        "plateBrief": "Empty neighborhood courtyard, no people.",
                    }
                    for i in range(1, count + 1)
                ],
            }
            for ch in ("ch1", "ch2", "ch3")
        ]
    }


def run_s4a(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s4a")
    plan, _ = load_approved_plan_v2(ctx, cid)
    appearance, _ = load_appearance_spec(ctx, cid)
    cfg = s4a_config(ctx)
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx))
    settings = qa_settings(ctx)
    warning = ensure_judge(ctx, settings)
    rev = next_rev(ctx.character_dir(cid) / "s4a-backgrounds", "bg")
    rev_dir = ctx.character_dir(cid) / "s4a-backgrounds" / rev
    state.transition("s4a", "RUNNING", rev=rev)
    try:
        guard = ranking_guard(ctx, cid, appearance.sourceReferenceRev)
        count = cfg["candidates_per_chapter"]
        inputs = {
            "plan-summary": plan_summary(plan),
            "appearance": {"era": "현대 한국", "ageRange": appearance.scope.ageRange},
            "settings": {"count": count},
            "name-guard": guard,
            "rules.md": (
                "현실적인 현대 한국 장소를 고른다. 실존 상호·브랜드·작품 이름은 쓰지 않는다. "
                "챕터 안의 후보는 서로 다른 장소다. ch1 첫 만남 → ch2 첫 데이트 → ch3 고백의 "
                "의미를 지킨다. 외모로 성격을 추정하지 않는다. plateBrief는 인물 없는 빈 장면이다."
            ),
        }
        out = call_agent(
            ctx,
            cid,
            budget,
            "s4a",
            "scene_scout",
            "background-candidates-output-v1",
            rev_dir / "workspace",
            inputs,
            [check_backgrounds(count, guard)],
            _example(count),
        )
        arc = {c.chapterId: c for c in plan.chapterArc}
        chapters = []
        for ch in out.chapters:
            candidates = []
            for candidate in ch.candidates:
                plate, qa = (
                    make_plate(
                        ctx,
                        cid,
                        budget,
                        "s4a",
                        rev,
                        rev_dir,
                        candidate.candidateId,
                        candidate,
                        guard,
                        settings,
                        warning,
                    )
                    if cfg["plates"]
                    else (None, None)
                )
                candidates.append(
                    dump(candidate) | {"plate": plate, "qa": dump(qa) if qa else None}
                )
            chapters.append(
                {
                    "chapterId": ch.chapterId,
                    "title": arc[ch.chapterId].title,
                    "arc": arc[ch.chapterId].arc,
                    "candidates": candidates,
                }
            )
        result = validate(
            "background-candidates-v1",
            {
                "characterId": cid,
                "backgroundRev": rev,
                "planRev": plan.planRev,
                "appearanceRev": appearance.appearanceRev,
                "aspectRatio": "9:16",
                "chapters": chapters,
            },
        )
        assert_no_names(result, guard)
        write_once_json(rev_dir / "background-candidates.json", dump(result))
        write_once_text(rev_dir / "gate-G4a.html", render_g4a_page(cid, rev, result))
        write_manifest(rev_dir)
    except FactoryError as e:
        ctx.state(cid).transition("s4a", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s4a", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G4a", "AWAITING_HUMAN", rev, None)
    return rev_dir
