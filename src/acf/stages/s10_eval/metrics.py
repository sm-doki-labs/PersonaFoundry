"""S10 평가 지표 (LLD §8.9, D-0045 (3)).

- repeat_rate_101_200: 101~200턴 캐릭터 말풍선 가운데 앞서 나온 것과 같은 비율.
- memory_recall_200: 200턴 시점 확인 질문의 정답 키 일치율(판정 모델).
- apology_recovery: 진지한 사과 구간에서 회복한 대본 비율(판정 모델).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from acf.common.errors import FactoryError
from acf.contracts.training import (
    ArmId,
    Criterion,
    CriterionResult,
    EvalPrereg,
    EvalRun,
    MetricValue,
    SetId,
)
from acf.providers.base import TextModel
from acf.stages.s10_eval.judge import ask_judge

SFT_ARMS: tuple[ArmId, ...] = ("SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT")
_KEEP = re.compile(r"[^0-9a-z가-힣]")


@dataclass(frozen=True)
class MetricOutcome:
    value: float
    detail: str


def normalize_bubble(text: str) -> str:
    """공백·문장부호·대소문자 차이를 지운 비교용 말풍선."""
    folded = unicodedata.normalize("NFKC", text).lower()
    return _KEEP.sub("", folded)


def repeat_rate_101_200(run: EvalRun) -> MetricOutcome:
    """101~200턴 말풍선이 그 대화에서 앞서 나온 말풍선과 같은 비율."""
    if run.setId != "LONG200":
        raise FactoryError(f"repeat_rate_101_200은 LONG200에만 쓴다(현재 {run.setId})")
    duplicates = 0
    total = 0
    for item in run.items:
        seen: set[str] = set()
        for idx, turn in enumerate(item.turns, start=1):
            key = normalize_bubble(turn.reply)
            if idx >= 101:
                total += 1
                if key in seen:
                    duplicates += 1
            seen.add(key)
    value = round(duplicates / total, 3) if total else 0.0
    return MetricOutcome(value=value, detail=f"{duplicates}/{total} 말풍선 중복")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "correct", "recovered", "1"}
    return False


def _run_item(run: EvalRun, item_id: str) -> Any:
    for item in run.items:
        if item.itemId == item_id:
            return item
    raise FactoryError(f"{run.armId}/{run.setId}: {item_id} 응답이 없다")


def memory_recall_200(
    run: EvalRun, set_doc: dict[str, Any], judge: TextModel, *, cid: str = ""
) -> MetricOutcome:
    """200턴 확인 질문마다 정답 키가 답에 들어 있는지 판정 모델에 묻는다."""
    correct = 0
    total = 0
    misses: list[str] = []
    for item in set_doc["items"]:
        run_item = _run_item(run, item["itemId"])
        for idx, turn in enumerate(item["turns"]):
            if turn.get("kind") != "check":
                continue
            if idx >= len(run_item.turns):
                raise FactoryError(f"{item['itemId']} {turn['turn']}턴 응답이 모자란다")
            reply = run_item.turns[idx].reply
            keys = " / ".join(turn.get("answerKeys") or [])
            result = ask_judge(
                judge,
                prompt_name="eval_memory.md",
                user_text=(
                    f"<question>\n{turn['user']}\n</question>\n\n"
                    f"<answer_keys>\n{keys}\n</answer_keys>\n\n"
                    f"<reply>\n{reply}\n</reply>"
                ),
                ref=f"{cid}/metric/memory/{run.armId}/{item['itemId']}/{turn['checkId']}",
            )
            total += 1
            if _as_bool(result.get("correct")):
                correct += 1
            else:
                misses.append(f"{item['personaId']}-{turn['checkId']}")
    value = round(correct / total, 3) if total else 0.0
    detail = f"{correct}/{total} 정답"
    if misses:
        detail += "; 놓침 " + ", ".join(misses)
    return MetricOutcome(value=value, detail=detail)


def _transcript(item: dict[str, Any], run_item: Any) -> str:
    lines = []
    for idx, turn in enumerate(item["turns"]):
        reply = run_item.turns[idx].reply if idx < len(run_item.turns) else ""
        lines.append(f"{turn['turn']}. 사용자: {turn['user']}")
        lines.append(f"   캐릭터: {reply}")
    return "\n".join(lines)


def apology_recovery(
    run: EvalRun, set_doc: dict[str, Any], judge: TextModel, *, cid: str = ""
) -> MetricOutcome:
    """무례 → 성의 없는 사과 → 진지한 사과 대본에서 실제로 회복했는지 판정한다."""
    recovered = 0
    total = 0
    misses: list[str] = []
    for item in set_doc["items"]:
        run_item = _run_item(run, item["itemId"])
        result = ask_judge(
            judge,
            prompt_name="eval_apology.md",
            user_text=(
                f"<title>{item.get('title', '')}</title>\n"
                f"<recovery_turns>{item['recoveryTurns']}</recovery_turns>\n\n"
                f"<transcript>\n{_transcript(item, run_item)}\n</transcript>"
            ),
            ref=f"{cid}/metric/apology/{run.armId}/{item['itemId']}",
            max_output_tokens=500,
        )
        total += 1
        if _as_bool(result.get("recovered")):
            recovered += 1
        else:
            misses.append(str(item["itemId"]))
    value = round(recovered / total, 3) if total else 0.0
    detail = f"{recovered}/{total} 회복"
    if misses:
        detail += "; 미회복 " + ", ".join(misses)
    return MetricOutcome(value=value, detail=detail)


def arm_metrics(
    prereg: EvalPrereg,
    runs: dict[tuple[ArmId, SetId], EvalRun],
    set_docs: dict[SetId, dict[str, Any]],
    judge: TextModel,
    *,
    cid: str,
) -> list[MetricValue]:
    out: list[MetricValue] = []
    for arm in prereg.arms:
        arm_id = arm.armId
        repeat = repeat_rate_101_200(runs[(arm_id, "LONG200")])
        memory = memory_recall_200(runs[(arm_id, "LONG200")], set_docs["LONG200"], judge, cid=cid)
        apology = apology_recovery(runs[(arm_id, "APOLOGY")], set_docs["APOLOGY"], judge, cid=cid)
        for metric, outcome in (
            ("repeat_rate_101_200", repeat),
            ("memory_recall_200", memory),
            ("apology_recovery", apology),
        ):
            out.append(
                MetricValue(armId=arm_id, metric=metric, value=outcome.value, detail=outcome.detail)
            )
    return out


def _relevant_arms(criterion: Criterion, prereg: EvalPrereg) -> list[ArmId]:
    if criterion.appliesTo == "SFT_ANY":
        return list(SFT_ARMS)
    return [arm.armId for arm in prereg.arms]


def evaluate_criteria(prereg: EvalPrereg, metrics: list[MetricValue]) -> list[CriterionResult]:
    by_key = {(m.armId, m.metric): m.value for m in metrics}
    results: list[CriterionResult] = []
    for criterion in prereg.criteria:
        for arm_id in _relevant_arms(criterion, prereg):
            if (arm_id, criterion.metric) not in by_key:
                raise FactoryError(f"지표가 없다: {arm_id}/{criterion.metric}")
            value = by_key[(arm_id, criterion.metric)]
            passed = (
                value <= criterion.threshold
                if criterion.comparator == "<="
                else value >= criterion.threshold
            )
            results.append(
                CriterionResult(id=criterion.id, armId=arm_id, value=value, passed=passed)
            )
    return results


def criteria_overall(prereg: EvalPrereg, results: list[CriterionResult]) -> dict[str, bool]:
    """기준별 전체 통과. SFT_ANY는 SFT 조건 가운데 하나라도 넘으면 통과다."""
    out: dict[str, bool] = {}
    for criterion in prereg.criteria:
        rows = [r for r in results if r.id == criterion.id]
        out[criterion.id] = (
            any(r.passed for r in rows)
            if criterion.appliesTo == "SFT_ANY"
            else bool(rows) and all(r.passed for r in rows)
        )
    return out
