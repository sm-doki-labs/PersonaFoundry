"""S7 상세 특질 (명세 §10.1, LLD §8.6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acf.common.budget import CallPlan
from acf.common.schema import dump
from acf.common.store import next_rev, write_manifest, write_once_json
from acf.pipeline.agent import AgentSpec, run_agent
from acf.pipeline.context import Context
from acf.stages.s3_plan.importer import load_approved_plan
from acf.stages.s7_traits.check import check_matches_plan, check_trait_sheet

CHOICE_GUIDE = """선택 학습 기준 5항목 (gemini-sft-poc character-factory-choice-learning-2026-10-01 §1):
- attention: 성과·감정·원인·행동·분위기 중 무엇을 먼저 받는지.
- interpretationPriority: 그 말을 어떻게 받아들이고 자기 기준·상대 감정·판단 근거·실행·경험 중 무엇을 먼저 지키는지.
- primaryResponse: 받아치기·경청·질문·편들기·제안·수락·거절 중 무엇을 먼저 수행하는지.
- expressionIntensity: 같은 대응에서 확신·능청·주도성·조심스러움·친밀감이 대사에 어떻게 나타나는지.
- switchConditions: 요청·거절·새 사실·실제 피해가 생기면 무엇을 바꾸고 무엇은 유지하는지."""

CARD_GUIDE = """카드 7요소 (Stanford 프리셋 schema 3.0 카드 구조):
- stance: 주도성·친화성을 요약한 기본 태세(예: 친화적 주도형). 측정값이 아니라 제작 요약이다.
- expressedTraits: 핵심 2개와 대비 1개. 각 항목은 행동으로 서술한다.
- judgmentPriorities: 주요 가치와 딜레마의 선택·이유·전환 조건.
- dialogueHabits: 답변 순서, 직접성, 질문, 근거, 어휘·어미 반복 패턴.
- situational: 조건 → 반응 → 복귀 또는 전환 조건.
- experiences: 사건·본인의 해석·현재 습관과의 연결 (허구)."""


def _example() -> dict[str, Any]:
    return {
        "schemaVersion": "trait-sheet-v1",
        "characterId": "<입력 그대로>",
        "planRev": "<입력 그대로>",
        "choice": {
            "attention": "상대의 말에서 성과보다 상대가 스스로를 깎아내리는 전제를 먼저 본다.",
            "interpretationPriority": "자기 기준을 먼저 지키고, 상대의 감정은 그 다음에 받는다.",
            "primaryResponse": "전제를 되받아친 뒤 자기 페이스로 제안한다.",
            "expressionIntensity": "단정적이고 능청스럽다. 변명이나 긴 설명을 붙이지 않는다.",
            "switchConditions": [
                "'조언 말고 들어 줘'라고 하면 분석·제안을 멈추고 듣는다. 거리와 말투는 유지한다.",
                "실제 잘못이 확인되면 짧게 인정하고 고친다. 자기 비하는 붙이지 않는다.",
            ],
        },
        "card": {
            "stance": "경쟁적 주도형",
            "bigFiveNotes": "미정",
            "expressedTraits": {"core": ["...행동으로 서술..."], "contrast": "..."},
            "judgmentPriorities": [
                {
                    "value": "...",
                    "dilemma": "...",
                    "choice": "...",
                    "reason": "...",
                    "switch": "...",
                }
            ],
            "dialogueHabits": {
                "order": "...",
                "directness": "...",
                "questions": "...",
                "evidence": "...",
                "lexicon": "...",
            },
            "situational": [{"condition": "...", "reaction": "...", "returnOrSwitch": "..."}],
            "experiences": [{"event": "...", "interpretation": "...", "habitLink": "..."}],
        },
        "references": [],
        "unresolved": ["card.bigFiveNotes"],
        "typeMappingAssumed": False,
    }


def plan_calls(cfg_retries: int) -> list[CallPlan]:
    return [
        CallPlan(
            "s7", f"Profiler 특질 시트 생성 (재시도 포함 최대 {1 + cfg_retries}회)", 1 + cfg_retries
        )
    ]


def run_s7(
    ctx: Context,
    cid: str,
    references: list[dict[str, str]] | None = None,
    reference_docs: dict[str, Any] | None = None,
) -> Path:
    """reference_docs: 참조 유형·프리셋 카드의 본문({파일명: JSON 또는 텍스트}). 에이전트 입력에 그대로 넣는다."""
    plan, plan_path = load_approved_plan(ctx, cid)
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    state.require_deps("s7")
    s7cfg = ctx.config.stage("s7")
    retries = int(s7cfg.get("max_check_retries", 3))
    budget = ctx.budget()
    plans = plan_calls(retries)
    budget.check_plan(plans)
    rev = next_rev(char_dir / "s7-traits", "tr")
    rev_dir = char_dir / "s7-traits" / rev
    state.transition("s7", "RUNNING", rev=rev)

    model = ctx.text_model(cid, budget)
    spec = AgentSpec(
        role="profiler", output_contract="trait-sheet-v1", stage="s7", max_check_retries=retries
    )
    inputs: dict[str, Any] = {
        "character-plan": dump(plan),
        "choice-guide.md": CHOICE_GUIDE,
        "card-guide.md": CARD_GUIDE,
        "references": references or [],
    }
    for name, doc in (reference_docs or {}).items():
        inputs[f"reference-doc-{name}"] = doc
    # 기획서 근거에 PRESET 참조가 있으면 카드 본문을 자동으로 넣는다 (Planner가 고른 프리셋).
    auto_refs: list[dict[str, str]] = list(references or [])
    for evs in plan.evidence.values():
        for ev in evs:
            if ev.kind == "PRESET" and ev.ref.startswith("STANFORD:"):
                parts = ev.ref.split(":")
                pid = parts[1]
                key = f"reference-doc-{pid}"
                if key not in inputs:
                    from acf.stages.s3_plan.draft import full_preset_card, load_catalog

                    try:
                        card = full_preset_card(load_catalog(ctx), pid)
                    except ValueError:
                        card = None
                    if card:
                        inputs[key] = card
                        ver = parts[2] if len(parts) > 2 else str(card.get("schema_version"))
                        if not any(r.get("id") == pid for r in auto_refs):
                            auto_refs.append({"kind": "STANFORD", "id": pid, "version": ver})
    inputs["references"] = auto_refs
    result = run_agent(
        spec,
        rev_dir / "workspace",
        inputs,
        [check_trait_sheet, check_matches_plan(plan.name, plan.coreTraits)],
        model,
        ref=f"{cid}/{rev}",
        contract_example=_example(),
        backend=ctx.agent_backend(cid, budget, "s7"),
    )
    if not result.ok:
        state.transition("s7", "CHECK_FAILED", rev=rev, error="; ".join(result.problems))
        raise SystemExit(
            f"S7 자동 검사 실패({result.attempts}회):\n- " + "\n- ".join(result.problems)
        )
    sheet = result.output
    write_once_json(rev_dir / "trait-sheet.json", dump(sheet))
    (rev_dir / "inputs.json").write_text(
        json.dumps(
            {"plan": plan_path.relative_to(char_dir).as_posix(), "references": references or []},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_manifest(rev_dir)
    # S7은 단독 관문이 없다. G6에서 프롬프트와 함께 승인된다.
    state.transition("s7", "AWAITING_HUMAN", rev=rev)
    return rev_dir / "trait-sheet.json"
