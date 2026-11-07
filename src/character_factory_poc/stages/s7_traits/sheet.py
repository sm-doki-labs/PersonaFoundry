"""S7 상세 특질 (명세 §10.1, LLD §8.6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s7_traits.check import (
    check_matches_plan,
    check_speech_level,
    check_trait_sheet,
)

CHOICE_GUIDE = """선택 학습 기준 5항목 (gemini-sft-poc character-factory-choice-learning-2026-10-01 §1):
- attention: 상대가 한 말에서 성과·감정·원인·행동·분위기 가운데 무엇을 먼저 받는지.
- interpretationPriority: 그 말을 어떻게 해석하고 자기 기준·상대 감정·판단 근거·실행·경험 가운데 무엇을 먼저 지키는지.
- primaryResponse: 단서가 없을 때 받아치기·경청·질문·편들기·제안·수락·거절 가운데 무엇을 먼저 하는지.
- expressionIntensity: 같은 대응에서 확신·능청·주도성·조심스러움·친밀감이 말에 드러나는 세기.
- switchConditions: 요청·거절·새 사실·실제 피해가 생기면 무엇을 바꾸고 무엇을 유지하는지."""

CARD_GUIDE = """카드 7요소 (Stanford 프리셋 schema 3.0 카드 구조):
- stance: 주도성과 친화성을 인물 주어의 완결 문장으로 요약한 기본 태세. 유형 이름이나 라벨을 쓰지 않는다.
- expressedTraits: 핵심 2개와 대비 1개. 각 항목은 행동으로 서술한다.
- judgmentPriorities: 지키려는 가치와 대화에서 실제로 생기는 딜레마의 선택·이유·전환 조건. 근거 없는 시비의 첫 반응 하나를 포함한다.
- dialogueHabits: 앞머리와 종결 기능, 직설성, 질문의 화행 기능과 빈도, 근거 습관, 어휘장과 말버릇의 자리·빈도. 상대높임 등급과 종결 형태는 정하지 않는다.
- situational: 계기와 적용하지 않는 경우 → 반응 → 복귀 또는 전환 조건.
- experiences: 사건·본인의 해석·현재 습관과의 연결 (허구)."""


def _example() -> dict[str, Any]:
    return {
        "schemaVersion": "trait-sheet-v1",
        "characterId": "<입력 그대로>",
        "planRev": "<입력 그대로>",
        "choice": {
            # D-0089: 예시 문장·따옴표 대사·유형 라벨을 두면 그대로 옮겨진다. 자리표시자만 둔다.
            "attention": "<상대가 한 말에서 먼저 받는 것>",
            "interpretationPriority": "<해석 습관과 그것이 바뀌는 조건>",
            "primaryResponse": "<단서가 없을 때 하는 행동>",
            "expressionIntensity": "<성격이 말에 드러나는 세기와 그 조건>",
            "switchConditions": [
                "<새 단서> → <유지할 것과 바꿀 대응>",
                "<새 단서> → <유지할 것과 바꿀 대응>",
            ],
        },
        "card": {
            "stance": "<기본 태세를 인물 주어의 완결 문장으로>",
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


def plan_calls(cfg_retries: int, *, deck_enabled: bool = False) -> list[CallPlan]:
    if deck_enabled:
        bound = 3 + min(1, cfg_retries) + 6
        return [
            CallPlan(
                "s7",
                "Gemini 특질 확정과 특질 장부(형식 재시도2회·검사 피드백1회씩 포함)",
                bound,
                est_cost_usd=None,
            )
        ]
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
    if "formation_profile" in ctx.config.stage("s7"):
        if ctx.config.stage("s7")["formation_profile"] == "ko-text-choice-voice-long-v2":
            from character_factory_poc.stages.s7_traits.choice_voice import run_choice_voice_s7

            return run_choice_voice_s7(ctx, cid)
        from character_factory_poc.stages.s7_traits.formation import run_formation_s7

        return run_formation_s7(ctx, cid, references, reference_docs)
    plan, plan_path = load_approved_plan(ctx, cid)
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    state.require_deps("s7")
    s7cfg = ctx.config.stage("s7")
    retries = int(s7cfg.get("max_check_retries", 3))
    if ctx.text_deck_enabled:
        retries = min(1, retries)
    budget = ctx.budget()
    plans = plan_calls(retries, deck_enabled=ctx.text_deck_enabled)
    budget.check_plan(plans)
    rev = next_rev(char_dir / "s7-traits", "tr")
    rev_dir = char_dir / "s7-traits" / rev
    state.transition("s7", "RUNNING", rev=rev)

    model = ctx.role_model(cid, budget, "profiler")
    spec = AgentSpec(
        role="profiler", output_contract="trait-sheet-v1", stage="s7", max_check_retries=retries
    )
    inputs: dict[str, Any] = {
        # D-0088: 대표 대사(voiceExamples)는 사람 검토용이다. 다음 단계에 넣으면 그대로 복제되므로
        # 성격 시트 입력에서 뺀다. 말투는 voiceSummary의 언어학적 기술로만 전달한다.
        "character-plan": {k: v for k, v in dump(plan).items() if k != "voiceExamples"},
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
                    from character_factory_poc.stages.s3_plan.common import (
                        full_preset_card,
                        load_catalog,
                    )

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
        [
            check_trait_sheet,
            check_matches_plan(plan.name, plan.coreTraits),
            check_speech_level(getattr(plan, "voiceSummary", "") or ""),
        ],
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
    if ctx.text_deck_enabled and ctx.config.stage("s7").get("trait_ledger", True):
        # D-0091: 흩어진 특질을 한 번씩 모은 장부. S8은 이 장부에서 대화 프롬프트를 조립한다.
        from character_factory_poc.stages.s7_traits.ledger import run_ledger

        ledger = run_ledger(
            ctx, cid, plan, sheet, rev_dir, budget, ctx.role_model(cid, budget, "trait_ledger")
        )
        write_once_json(rev_dir / "trait-ledger.json", dump(ledger))
    if ctx.text_deck_enabled:
        calls = [
            c
            for c in ctx.ledger(cid).calls()
            if c["ok"] and c["stage"] == "s7" and c["ref"].startswith(f"{cid}/{rev}#")
        ]
        last = calls[-1] if calls else None
        write_once_json(
            rev_dir / "text-deck-binding.json",
            dict(
                status="recorded" if last else "unknown",
                binding=getattr(model, "binding", None),
                responseModel=last["model"] if last else None,
                callRef=last["ref"] if last else None,
                traitSheetSha256=sha256_file(rev_dir / "trait-sheet.json"),
            ),
        )
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
