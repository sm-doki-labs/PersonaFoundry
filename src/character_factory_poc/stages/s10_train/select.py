"""S10t 체크포인트 선택 (D-0077, 품질 운영 규격 01·03).

원격 선별 스크립트(screen_qlora.py)가 남긴 첫 출력만으로 고른다. 손실은 기록만 한다.

1. 무결성: 선별 파일이 없거나 체크포인트 응답이 하나도 없으면 BLOCKED_INTEGRITY.
2. 결함 지표: 팔마다 빈 답·잘림·반복 루프 비율, 연속 대화 조기 중단, 답 길이 중앙값.
3. 적격: epoch 순으로 걸으며 결함이 나빠지지 않는 마지막 체크포인트까지(머스크 PLAN_v3 4.4).
4. 짝 판정: 적격 체크포인트와 base를 정순·역순으로 비교하고, 두 순서가 같은 쪽일 때만 센다.
5. 선택: consensus 승수 최다, 동률이면 마지막 적격. base가 직접 비교에서 이기면 KEEP_INCUMBENT.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from character_factory_poc.common.schema import dump, register, validate
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.training import Checkpoint, TrainingRun
from character_factory_poc.providers.base import (
    ChatRequest,
    Message,
    TextModel,
    extract_json_object,
)

Decision = Literal[
    "RELEASE_ACCEPTED",
    "MODEL_ACCEPTED",
    "DEVELOPMENT_RECOMMENDED",
    "KEEP_INCUMBENT",
    "INCONCLUSIVE",
    "BLOCKED_INTEGRITY",
    "BLOCKED_QUALITY",
]
Pick = Literal["A", "B", "TIE", "INVALID"]
Consensus = Literal["A", "B", "TIE", "ORDER_UNSTABLE", "MISSING"]

BASE_ARM = "base"
PROMPT_NAME = "checkpoint_pair_judge.md"
DEFECT_KEYS = ("empty", "truncated", "loop")
MAX_DEFECT_RATE = 0.2
MAX_DEFECT_RISE = 0.05
MIN_LENGTH_RATIO = 0.5
LOOP_NGRAM = 4
LOOP_REPEATS = 3
HISTORY_MESSAGES = 12

RULE = (
    "선별 첫 출력만 쓴다. 체크포인트를 epoch 순으로 걸으며, 응답 커버리지가 계획보다 모자라거나 "
    f"빈 답·잘림·반복 루프 비율 가운데 하나가 {MAX_DEFECT_RATE:g}를 넘거나, 직전 적격보다 "
    f"{MAX_DEFECT_RISE:g} 넘게 오르거나, 답 길이 중앙값이 직전 적격의 {MIN_LENGTH_RATIO:g}배 "
    "미만이면 그 체크포인트부터 제외한다(결함이 나빠지지 않는 마지막 체크포인트까지 적격). "
    "적격 체크포인트와 base를 한 턴 과제에서 정순·역순으로 짝 판정하고, 두 순서가 같은 쪽일 때만 "
    "consensus로 센다(ORDER_UNSTABLE·형식 오류는 미집계). consensus 승수가 가장 많은 체크포인트를 "
    "고르고 동률이면 마지막 적격을 고른다. base가 그 체크포인트와의 직접 비교에서 더 많이 이기면 "
    "KEEP_INCUMBENT다. validation loss는 기록만 하고 선택에 쓰지 않는다."
)


@dataclass(frozen=True)
class SelectionResult:
    decision: str
    checkpoint_id: str | None
    checkpoint_ref: str | None
    record_path: Path


# ---- 기록 계약 ------------------------------------------------------------------------------


class Ratio(Strict):
    numerator: int
    denominator: int
    rate: float | None = None


class ArmMetrics(Strict):
    arm: str
    role: Literal["base", "checkpoint"]
    epoch: int | float | None = None
    coverage: Ratio = Field(description="응답이 있는 과제 수 / 계획 과제 수")
    generations: int = 0
    empty: Ratio
    truncated: Ratio = Field(description="finish가 stop이 아닌 생성")
    loop: Ratio = Field(description="어절 4-gram 3회 이상 또는 직전 자기 답과 정규화 후 동일")
    earlyStop: Ratio = Field(description="계획한 턴을 다 못 채운 연속 대화")
    lengthMedian: float | None = Field(default=None, description="비지 않은 답의 글자 수 중앙값")
    eligible: bool | None = Field(default=None, description="base는 None")
    exclusion: str = ""


class CheckpointLoss(Strict):
    checkpointId: str
    epoch: int | float | None = None
    step: int | None = None
    validationLoss: float | None = None
    lossUse: Literal["recorded_only"] = "recorded_only"


class PairJudgment(Strict):
    armA: str
    armB: str
    taskId: str
    forward: Pick
    reverse: Pick = Field(description="역순 판정을 정순 라벨(A=armA)로 되돌린 값")
    consensus: Consensus
    winner: str | None = Field(default=None, description="consensus가 A·B일 때 이긴 팔")
    reason: str = ""


class HeadToHead(Strict):
    armA: str
    armB: str
    winsA: int
    winsB: int
    ties: int
    orderUnstable: int
    missing: int


class ChosenCheckpoint(Strict):
    checkpointId: str
    ref: str
    epoch: int | float | None = None


@register("checkpoint-selection-v1")
class CheckpointSelectionDoc(Strict):
    schemaVersion: Literal["checkpoint-selection-v1"] = "checkpoint-selection-v1"
    characterId: str
    datasetRev: str
    datasetDigest: str
    rule: str
    splitUse: Literal["development_shared_context"] = Field(
        default="development_shared_context",
        description="손실 검증 대화에서 뽑은 선별 과제라 final_holdout이 아니다",
    )
    screenFile: str
    screenRows: int = 0
    plannedTasks: int
    plannedArms: list[str]
    arms: list[ArmMetrics] = Field(default_factory=list)
    checkpointLosses: list[CheckpointLoss] = Field(default_factory=list)
    eligibleCheckpoints: list[str] = Field(default_factory=list)
    judgeModel: str | None = None
    judgeItems: int
    pairs: list[PairJudgment] = Field(default_factory=list)
    headToHead: list[HeadToHead] = Field(default_factory=list)
    wins: dict[str, int] = Field(default_factory=dict, description="consensus 승수만 센다")
    plannedJudgments: int = Field(default=0, description="판정 호출 계획 수(비교 × 정순·역순)")
    validJudgments: int = Field(default=0, description="형식이 맞은 판정 호출 수")
    consensusComparisons: int = 0
    orderUnstable: int = 0
    bestCheckpoint: str | None = Field(default=None, description="판정상 최선. base 비교용")
    decision: Decision
    chosen: ChosenCheckpoint | None = None
    reasons: list[str] = Field(default_factory=list)


# ---- 선별 파일 읽기 ---------------------------------------------------------------------------


def _read_rows(path: Path, reasons: list[str]) -> dict[tuple[str, str], dict[str, Any]]:
    """(arm, taskId)별 첫 행만 쓴다. 다시 뽑은 행이 있어도 첫 출력이 기준이다."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    bad = dup = 0
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            key = (str(row["arm"]), str(row["taskId"]))
            turns = row.get("turns")
            if not isinstance(turns, list):
                raise TypeError("turns")
        except (ValueError, KeyError, TypeError):
            bad += 1
            continue
        if key in rows:
            dup += 1
            continue
        rows[key] = row
    if bad:
        reasons.append(f"선별 파일에서 읽지 못한 행 {bad}개를 뺐다")
    if dup:
        reasons.append(f"같은 팔·과제의 중복 행 {dup}개는 첫 행만 썼다")
    return rows


def _ratio(num: int, den: int) -> Ratio:
    return Ratio(numerator=num, denominator=den, rate=round(num / den, 4) if den else None)


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).lower()


def has_ngram_loop(text: str, n: int = LOOP_NGRAM, repeats: int = LOOP_REPEATS) -> bool:
    words = text.split()
    if len(words) < n:
        return False
    counts = Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
    return max(counts.values()) >= repeats


def _arm_metrics(
    arm: str,
    role: Literal["base", "checkpoint"],
    epoch: int | float | None,
    tasks: list[dict[str, Any]],
    rows: dict[tuple[str, str], dict[str, Any]],
) -> ArmMetrics:
    covered = gens = empty = truncated = loops = 0
    multi_total = multi_short = 0
    lengths: list[int] = []
    for task in tasks:
        row = rows.get((arm, str(task["taskId"])))
        if row is None or not row["turns"]:
            continue
        covered += 1
        prev = ""
        for turn in row["turns"]:
            text = str(turn.get("text") or "").strip()
            gens += 1
            if not text:
                empty += 1
            else:
                lengths.append(len(text))
            if turn.get("finish") != "stop":
                truncated += 1
            if text and (has_ngram_loop(text) or (prev and _norm(text) == _norm(prev))):
                loops += 1
            prev = text
        if task.get("kind") == "multi":
            multi_total += 1
            if len(row["turns"]) < len(task.get("userTurns") or []):
                multi_short += 1
    return ArmMetrics(
        arm=arm,
        role=role,
        epoch=epoch,
        coverage=_ratio(covered, len(tasks)),
        generations=gens,
        empty=_ratio(empty, gens),
        truncated=_ratio(truncated, gens),
        loop=_ratio(loops, gens),
        earlyStop=_ratio(multi_short, multi_total),
        lengthMedian=float(statistics.median(lengths)) if lengths else None,
    )


def _rate(m: ArmMetrics, key: str) -> float:
    return getattr(m, key).rate or 0.0


def _complete(m: ArmMetrics) -> bool:
    return m.coverage.denominator > 0 and m.coverage.numerator == m.coverage.denominator


def _exclusion(m: ArmMetrics, prev: ArmMetrics | None) -> str:
    if not _complete(m):
        return f"응답 커버리지 {m.coverage.numerator}/{m.coverage.denominator}"
    over = [k for k in DEFECT_KEYS if _rate(m, k) > MAX_DEFECT_RATE]
    if over:
        return f"결함률 {MAX_DEFECT_RATE:g} 초과: " + ", ".join(
            f"{k} {_rate(m, k):.3f}" for k in over
        )
    if prev is None:
        return ""
    rose = [k for k in DEFECT_KEYS if _rate(m, k) - _rate(prev, k) > MAX_DEFECT_RISE]
    if rose:
        return f"직전 적격 {prev.arm} 대비 결함 악화: " + ", ".join(
            f"{k} {_rate(prev, k):.3f}→{_rate(m, k):.3f}" for k in rose
        )
    if prev.lengthMedian and (m.lengthMedian or 0.0) < MIN_LENGTH_RATIO * prev.lengthMedian:
        return (
            f"답 길이 중앙값 {prev.lengthMedian:g}→{m.lengthMedian or 0:g} (직전 적격의 절반 미만)"
        )
    return ""


def _ordered(checkpoints: list[Checkpoint]) -> list[Checkpoint]:
    indexed = list(enumerate(checkpoints))
    indexed.sort(key=lambda p: (p[1].epoch is None, p[1].epoch or 0, p[0]))
    return [c for _, c in indexed]


def join_ref(prefix: str, ref: str) -> str:
    """접두어 끝에 '/'가 없으면 하나 넣어 잇는다. 'vast:job/'처럼 끝난 접두어는 그대로 붙인다."""
    if not prefix:
        return ref
    if prefix.endswith("/") or ref.startswith("/"):
        return prefix + ref
    return f"{prefix}/{ref}"


# ---- 짝 판정 ---------------------------------------------------------------------------------


def load_judge_prompt() -> str:
    return resources.files("character_factory_poc.prompts").joinpath(PROMPT_NAME).read_text("utf-8")


def _first_text(row: dict[str, Any] | None) -> str:
    if row is None or not row["turns"]:
        return ""
    return str(row["turns"][0].get("text") or "").strip()


def _context_text(task: dict[str, Any]) -> tuple[str, str]:
    """(대화 이력, 마지막 사용자 발화). system은 persona_text로 따로 준다."""
    messages = [m for m in task.get("messages") or [] if m.get("role") != "system"]
    user = ""
    if messages and messages[-1].get("role") == "user":
        user = str(messages[-1]["content"])
        messages = messages[:-1]
    lines = []
    for m in messages[-HISTORY_MESSAGES:]:
        who = "사용자" if m.get("role") == "user" else "캐릭터"
        lines.append(f"{who}: {m.get('content', '')}")
    return "\n".join(lines), user


def _ask(judge: TextModel, role: str, user_text: str, ref: str) -> tuple[Pick, str]:
    response = judge.complete(
        ChatRequest(
            kind="JUDGE",
            stage="s10t",
            messages=(Message("system", role), Message("user", user_text)),
            ref=ref,
            max_output_tokens=400,
            temperature=0.0,
            response_json=True,
        )
    )
    try:
        obj = extract_json_object(response.text)
    except ValueError:
        return "INVALID", "판정 응답이 JSON 객체가 아니다"
    if not isinstance(obj, dict):
        return "INVALID", "판정 응답이 객체가 아니다"
    winner = str(obj.get("winner", "")).strip().upper()
    if winner not in {"A", "B", "TIE"}:
        return "INVALID", f"winner 값이 형식에 맞지 않는다: {obj.get('winner')!r}"
    return winner, str(obj.get("reason", "")).strip()  # type: ignore[return-value]


def _consensus(forward: Pick, reverse: Pick) -> Consensus:
    if forward == "INVALID" or reverse == "INVALID":
        return "MISSING"
    return forward if forward == reverse else "ORDER_UNSTABLE"


def _judge_pairs(
    judge: TextModel,
    *,
    participants: list[str],
    single_tasks: list[dict[str, Any]],
    rows: dict[tuple[str, str], dict[str, Any]],
    persona_text: str,
    judge_items: int,
    ref_root: str,
) -> tuple[list[PairJudgment], int, int]:
    role = load_judge_prompt()
    pairs: list[PairJudgment] = []
    planned = valid = 0
    for i, arm_a in enumerate(participants):
        for arm_b in participants[i + 1 :]:
            items: list[tuple[dict[str, Any], str, str]] = []
            for task in single_tasks:
                if len(items) >= judge_items:
                    break
                a = _first_text(rows.get((arm_a, str(task["taskId"]))))
                b = _first_text(rows.get((arm_b, str(task["taskId"]))))
                if a and b:
                    items.append((task, a, b))
            for task, a, b in items:
                history, user = _context_text(task)
                base = (
                    f"<persona>\n{persona_text}\n</persona>\n\n"
                    f"<history>\n{history}\n</history>\n\n"
                    f"<user_turn>\n{user}\n</user_turn>\n\n"
                )
                ref = f"{ref_root}/{arm_a}-vs-{arm_b}/{task['taskId']}"
                f_pick, f_reason = _ask(
                    judge, role, base + f"<A>\n{a}\n</A>\n\n<B>\n{b}\n</B>", f"{ref}/forward"
                )
                r_raw, r_reason = _ask(
                    judge, role, base + f"<A>\n{b}\n</A>\n\n<B>\n{a}\n</B>", f"{ref}/reverse"
                )
                r_pick: Pick = {"A": "B", "B": "A"}.get(r_raw, r_raw)  # type: ignore[assignment]
                planned += 2
                valid += (f_pick != "INVALID") + (r_pick != "INVALID")
                consensus = _consensus(f_pick, r_pick)
                winner = {"A": arm_a, "B": arm_b}.get(consensus)
                reason = " | ".join(s for s in (f_reason, r_reason) if s)[:600]
                pairs.append(
                    PairJudgment(
                        armA=arm_a,
                        armB=arm_b,
                        taskId=str(task["taskId"]),
                        forward=f_pick,
                        reverse=r_pick,
                        consensus=consensus,
                        winner=winner,
                        reason=reason,
                    )
                )
    return pairs, planned, valid


def _head_to_head(participants: list[str], pairs: list[PairJudgment]) -> list[HeadToHead]:
    out: list[HeadToHead] = []
    for i, arm_a in enumerate(participants):
        for arm_b in participants[i + 1 :]:
            mine = [p for p in pairs if p.armA == arm_a and p.armB == arm_b]
            out.append(
                HeadToHead(
                    armA=arm_a,
                    armB=arm_b,
                    winsA=sum(p.consensus == "A" for p in mine),
                    winsB=sum(p.consensus == "B" for p in mine),
                    ties=sum(p.consensus == "TIE" for p in mine),
                    orderUnstable=sum(p.consensus == "ORDER_UNSTABLE" for p in mine),
                    missing=sum(p.consensus == "MISSING" for p in mine),
                )
            )
    return out


def _direct(h2h: list[HeadToHead], x: str, y: str) -> tuple[int, int]:
    """x와 y의 직접 비교에서 (x 승, y 승)."""
    for h in h2h:
        if (h.armA, h.armB) == (x, y):
            return h.winsA, h.winsB
        if (h.armA, h.armB) == (y, x):
            return h.winsB, h.winsA
    return 0, 0


# ---- 진입점 ---------------------------------------------------------------------------------


def select_checkpoint(
    *,
    run: TrainingRun,
    artifact_dir: Path,
    tasks: list[dict],
    persona_text: str,
    judge: TextModel | None,
    out_path: Path,
    judge_items: int = 8,
    ref_prefix: str = "",
) -> SelectionResult:
    screen = Path(artifact_dir) / "screen" / "responses.jsonl"
    reasons: list[str] = []
    ordered = _ordered(list(run.checkpoints))
    by_id = {c.checkpointId: c for c in ordered}
    record: dict[str, Any] = {
        "characterId": run.characterId,
        "datasetRev": run.datasetRev,
        "datasetDigest": run.datasetDigest,
        "rule": RULE,
        "screenFile": "screen/responses.jsonl",
        "plannedTasks": len(tasks),
        "plannedArms": [c.checkpointId for c in ordered],
        "checkpointLosses": [
            CheckpointLoss(
                checkpointId=c.checkpointId,
                epoch=c.epoch,
                step=c.step,
                validationLoss=c.validationLoss,
            )
            for c in ordered
        ],
        "judgeModel": getattr(judge, "model", None) if judge is not None else None,
        "judgeItems": judge_items,
        "reasons": reasons,
    }

    def finish(decision: str, chosen: Checkpoint | None, **extra: Any) -> SelectionResult:
        if chosen is not None:
            record["chosen"] = ChosenCheckpoint(
                checkpointId=chosen.checkpointId,
                ref=join_ref(ref_prefix, chosen.ref),
                epoch=chosen.epoch,
            )
        doc = validate("checkpoint-selection-v1", record | extra | {"decision": decision})
        write_once_json(Path(out_path), dump(doc))
        return SelectionResult(
            decision=decision,
            checkpoint_id=chosen.checkpointId if chosen else None,
            checkpoint_ref=join_ref(ref_prefix, chosen.ref) if chosen else None,
            record_path=Path(out_path),
        )

    if not ordered:
        reasons.append("학습 실행 기록에 체크포인트가 없다")
        return finish("BLOCKED_INTEGRITY", None)
    if not tasks:
        reasons.append("선별 과제 계획이 비어 있다")
        return finish("BLOCKED_INTEGRITY", None)
    if not screen.is_file():
        reasons.append(f"선별 파일이 없다: {screen}")
        return finish("BLOCKED_INTEGRITY", None)

    rows = _read_rows(screen, reasons)
    record["screenRows"] = len(rows)
    known = {BASE_ARM, *by_id}
    unknown = sorted({arm for arm, _ in rows} - known)
    if unknown:
        reasons.append("학습 기록에 없는 팔의 응답은 뺐다: " + ", ".join(unknown))
    planned_ids = {str(t["taskId"]) for t in tasks}
    has_base = any(arm == BASE_ARM and tid in planned_ids for arm, tid in rows)
    if has_base:
        record["plannedArms"] = [BASE_ARM, *record["plannedArms"]]

    metrics: list[ArmMetrics] = []
    base_metrics: ArmMetrics | None = None
    if has_base:
        base_metrics = _arm_metrics(BASE_ARM, "base", None, tasks, rows)
        metrics.append(base_metrics)
    ck_metrics = [_arm_metrics(c.checkpointId, "checkpoint", c.epoch, tasks, rows) for c in ordered]

    if all(m.coverage.numerator == 0 for m in ck_metrics):
        reasons.append("모든 체크포인트의 선별 응답이 없다")
        record["arms"] = metrics + ck_metrics
        return finish("BLOCKED_INTEGRITY", None)

    eligible: list[str] = []
    prev: ArmMetrics | None = None
    stopped = ""
    first_block = ""
    for i, m in enumerate(ck_metrics):
        if stopped:
            ck_metrics[i] = m.model_copy(
                update={
                    "eligible": False,
                    "exclusion": f"앞 체크포인트에서 탐색이 멈췄다({stopped})",
                }
            )
            continue
        why = _exclusion(m, prev)
        if why:
            stopped = m.arm
            first_block = first_block or why
            ck_metrics[i] = m.model_copy(update={"eligible": False, "exclusion": why})
            continue
        ck_metrics[i] = m.model_copy(update={"eligible": True})
        eligible.append(m.arm)
        prev = m
    record["arms"] = metrics + ck_metrics
    record["eligibleCheckpoints"] = eligible

    if not eligible:
        reasons.append(f"적격 체크포인트가 없다: {ordered[0].checkpointId} {first_block}")
        decision = (
            "BLOCKED_INTEGRITY" if first_block.startswith("응답 커버리지") else "BLOCKED_QUALITY"
        )
        return finish(decision, None)
    if stopped:
        reasons.append(f"{stopped}부터 적격에서 뺐다")
    last = by_id[eligible[-1]]

    if judge is None:
        reasons.append("판정 모델이 없어 마지막 적격 체크포인트를 잠정으로 둔다")
        return finish("INCONCLUSIVE", last)

    participants = list(eligible)
    if base_metrics is not None:
        if _complete(base_metrics):
            participants = [BASE_ARM, *participants]
        else:
            reasons.append(
                f"base 응답 커버리지 {base_metrics.coverage.numerator}/"
                f"{base_metrics.coverage.denominator}라 짝 판정에서 뺐다"
            )
    single = [t for t in tasks if t.get("kind") == "single"]
    pairs, planned, valid = _judge_pairs(
        judge,
        participants=participants,
        single_tasks=single,
        rows=rows,
        persona_text=persona_text,
        judge_items=judge_items,
        ref_root=f"{run.characterId}/{run.datasetRev}/select",
    )
    h2h = _head_to_head(participants, pairs)
    wins = {arm: sum(p.winner == arm for p in pairs) for arm in participants}
    consensus_n = sum(p.consensus in {"A", "B", "TIE"} for p in pairs)
    extra: dict[str, Any] = {
        "pairs": pairs,
        "headToHead": h2h,
        "wins": wins,
        "plannedJudgments": planned,
        "validJudgments": valid,
        "consensusComparisons": consensus_n,
        "orderUnstable": sum(p.consensus == "ORDER_UNSTABLE" for p in pairs),
    }
    if consensus_n == 0:
        reasons.append(
            f"순서를 바꿔도 같은 판정이 하나도 없다(비교 {len(pairs)}건, 유효 판정 "
            f"{valid}/{planned}). 마지막 적격 체크포인트를 잠정으로 둔다"
        )
        return finish("INCONCLUSIVE", last, **extra)

    top = max(wins[c] for c in eligible)
    best = [c for c in eligible if wins[c] == top][-1]
    extra["bestCheckpoint"] = best
    if BASE_ARM in participants:
        base_w, best_w = _direct(h2h, BASE_ARM, best)
        if base_w > best_w:
            reasons.append(f"base가 {best}와의 직접 비교에서 {base_w}:{best_w}로 앞선다")
            return finish("KEEP_INCUMBENT", None, **extra)
        reasons.append(f"{best}가 base와의 직접 비교에서 {best_w}:{base_w}")
    reasons.append(f"{best} consensus 승 {top} (동률이면 마지막 적격)")
    return finish("DEVELOPMENT_RECOMMENDED", by_id[best], **extra)
