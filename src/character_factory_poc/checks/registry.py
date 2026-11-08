"""단계별 검사 묶음 (LLD §8). 에이전트 러너와 'cfp check'가 같은 함수를 쓴다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.schema import validate


def _read_input(workspace: Path, name: str) -> Any:
    p = workspace / "inputs" / name
    if not p.exists():
        return None
    if p.suffix == ".json":
        return json.loads(p.read_text("utf-8"))
    return p.read_text("utf-8")


def stage_checks(stage: str, workspace: Path) -> tuple[str, list]:
    """(계약 이름, 검사 함수 목록). 검사 함수는 검증된 모델을 받아 문제 목록을 돌려준다."""
    shape_only = {
        "cv-requirements": "seed-requirements-draft-v1",
        "cv-choices": "plan-variants-output-v2",
        "cv-design": "formation-draft-v2",
        "cv-beats": "formation-beats-draft-v1",
        "cv-render": "rendered-dialogues-draft-v1",
    }
    if stage in shape_only:
        return shape_only[stage], []
    if stage == "s1":
        from character_factory_poc.stages.s1_reference.features import check_features

        people = _read_input(workspace, "people.json") or []
        vocab = _read_input(workspace, "vocab.json") or {}
        return "appearance-features-v1", [check_features(people, vocab)]
    if stage == "s7":
        from character_factory_poc.stages.s7_traits.check import (
            check_matches_plan,
            check_speech_level,
            check_trait_sheet,
        )

        plan = _read_input(workspace, "character-plan.json") or {}
        return "trait-sheet-v1", [
            check_trait_sheet,
            check_matches_plan(plan.get("name", ""), plan.get("coreTraits", [])),
            check_speech_level(plan.get("voiceSummary", "") or ""),
        ]
    if stage == "s8":
        from character_factory_poc.stages.s8_prompts.build import make_section_checks

        sections = _read_input(workspace, "sections.json") or []
        budget = _read_input(workspace, "shortBudget.json") or {}
        return "prompter-output-v1", [make_section_checks(sections, budget)]
    # D-0033 흐름의 에이전트 단계 표지. 각 단계 모듈의 codex_checks가 같은 검사를 돌려준다.
    modules = {
        "s3-variants": "character_factory_poc.stages.s3_plan.variants",
        "s3-twin": "character_factory_poc.stages.s3_plan.twin",
        "s3-own": "character_factory_poc.stages.s3_plan.own",
        "s3r": "character_factory_poc.stages.s3r_refs.select",
        "s0": "character_factory_poc.stages.s0_source.run",
        "s4a": "character_factory_poc.stages.s4a_backgrounds.run",
        "s4b-scene": "character_factory_poc.stages.s4b_poses.run",
        "s4b-pose": "character_factory_poc.stages.s4b_poses.run",
    }
    if stage in modules:
        import importlib

        return importlib.import_module(modules[stage]).codex_checks(stage, workspace)
    raise ValueError(f"검사가 정의되지 않은 단계: {stage}")


def run_checks(stage: str, workspace: Path, output_path: Path | None = None) -> list[str]:
    """output.json을 계약으로 검증하고 단계 검사를 돌린다. 문제 목록(비면 통과)."""
    workspace = Path(workspace)
    out = output_path or (workspace / "output.json")
    if not out.exists():
        return [f"{out.name}이 없다"]
    try:
        raw = json.loads(out.read_text("utf-8"))
    except json.JSONDecodeError as e:
        return [f"{out.name}이 JSON이 아니다: {e}"]
    contract, checks = stage_checks(stage, workspace)
    from character_factory_poc.common.errors import ValidationFailed

    try:
        model = validate(contract, raw)
    except ValidationFailed as e:
        return [f"계약 {contract} 검증 실패: {p}" for p in e.problems]
    problems: list[str] = []
    for c in checks:
        problems.extend(c(model))
    return problems
