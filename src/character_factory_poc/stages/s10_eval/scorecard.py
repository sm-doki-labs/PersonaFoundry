"""S10 축별 점수표·결정 초안·개선 과제 장부 (D-0078, 정책 qlora-authored-v1).

기존 지표(repeat_rate_101_200, memory_recall_200, apology_recovery)와 LLM 짝 판정을 정책
evaluation.suites에 매핑해 축별 커버리지(측정됨·부분·미측정)와 분자·분모를 만든다. 정책의 결정값
가운데 하나를 자동 초안으로 계산하고, 실패 신호를 improvement.failureTypes에 매핑해
improvement-tasks-v1 장부를 만든다.

- 결정은 초안이다. G8의 사람 결정을 대신하지 않는다. 판정은 llm_only라 RELEASE_ACCEPTED·
  MODEL_ACCEPTED는 자동으로 내지 않는다.
- 정책 수치의 source가 "proposal"이면 검증된 최적값이 아니라 운영 시작값이고, 기록에
  startingValue=True로 그대로 드러낸다.
- 지금 세트(OE·SE·APOLOGY·LONG200)로 재지 못하는 문항군은 NOT_MEASURED로 남긴다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from character_factory_poc.common import qlora_policy as qp
from character_factory_poc.common.canonical import sha256_file, sha256_of
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import register, validate
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.training import EvalPrereg, EvalRun, MetricValue

POLICY_NAME = "qlora-authored-v1"
BASE_ARM = "LONG_BASE"
SFT_ARMS = ("SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT")
AUTO_FORBIDDEN = ("RELEASE_ACCEPTED", "MODEL_ACCEPTED")
REVIEW_MODE = "llm_only"
DRAFT_NOTE = (
    "이 결정은 정책 규칙으로 계산한 초안이다. G8의 사람 결정을 대신하지 않는다. 판정이 "
    "llm_only라 RELEASE_ACCEPTED·MODEL_ACCEPTED는 자동으로 내지 않는다."
)

Coverage = Literal["MEASURED", "PARTIAL", "NOT_MEASURED"]
Decision = Literal[
    "RELEASE_ACCEPTED",
    "MODEL_ACCEPTED",
    "DEVELOPMENT_RECOMMENDED",
    "KEEP_INCUMBENT",
    "INCONCLUSIVE",
    "BLOCKED_INTEGRITY",
    "BLOCKED_QUALITY",
]
ComponentState = Literal["measured", "relative", "not_measured"]
InterventionKind = Literal["eval", "prompt", "data", "checkpoint"]

_FRACTION = re.compile(r"(\d+)\s*/\s*(\d+)")


# ---- 기록 계약 ------------------------------------------------------------------------------


class PolicyNumber(Strict):
    """정책 수치 하나. source가 proposal이면 운영 시작값이다."""

    value: float | int | None = None
    source: str = ""
    startingValue: bool = Field(
        default=False, description="source가 proposal이면 True(검증된 값이 아니라 운영 시작값)"
    )
    note: str = ""


class Measure(Strict):
    component: str
    armId: str
    metric: str
    numerator: int | None = None
    denominator: int | None = None
    rate: float | None = None
    gate: str | None = Field(default=None, description="정책 evaluation.gates 키 또는 prereg 기준")
    comparator: Literal["<=", ">="] | None = None
    threshold: PolicyNumber | None = None
    passed: bool | None = None
    detail: str = ""


class PairTally(Strict):
    """한 문항군·한 조건 쌍의 LLM 짝 판정. SPLIT(ORDER_UNSTABLE)은 승수에서 뺀다."""

    setIds: list[str]
    armA: str
    armB: str
    winsA: int = 0
    winsB: int = 0
    ties: int = 0
    split: int = 0
    total: int = 0

    @property
    def consensus(self) -> int:
        return self.winsA + self.winsB + self.ties


class Component(Strict):
    name: str
    state: ComponentState
    by: str = Field(description="무엇으로 쟀는지, 못 쟀으면 왜 못 쟀는지")


class SuiteCoverage(Strict):
    suiteId: str
    purpose: str
    axes: list[str] = Field(default_factory=list)
    coverage: Coverage
    sets: list[str] = Field(default_factory=list)
    components: list[Component]
    plan: dict[str, PolicyNumber] = Field(
        default_factory=dict, description="정책이 계획한 규모. 지금 세트의 분모와 비교한다"
    )
    measures: list[Measure] = Field(default_factory=list)
    pairs: list[PairTally] = Field(default_factory=list)
    note: str = ""


class CriticalCheck(Strict):
    errorId: str
    coverage: Coverage
    by: str
    measures: list[Measure] = Field(default_factory=list)


class ChosenSummary(Strict):
    checkpointId: str
    ref: str
    epoch: int | float | None = None


class CheckpointSelectionSummary(Strict):
    ref: str
    sha256: str
    decision: str | None = None
    chosen: ChosenSummary | None = None
    bestCheckpoint: str | None = None
    matchesBinding: bool | None = Field(
        default=None, description="선택 체크포인트가 평가한 SHORT_GEMMA_SFT binding과 같은가"
    )
    meaning: str = ""
    reasons: list[str] = Field(default_factory=list)


class Evidence(Strict):
    armId: str
    metric: str
    numerator: int | None = None
    denominator: int | None = None
    rate: float | None = None
    comparator: str | None = None
    threshold: PolicyNumber | None = None
    detail: str = ""


class FailureMapping(Strict):
    confidence: Literal["exact", "approximate", "unmapped"]
    policySignal: str | None = None
    policyCauseLocation: str | None = None
    matchedTerms: list[str] = Field(
        default_factory=list, description="정책 signal·firstIntervention에서 찾은 낱말"
    )
    rationale: str
    alternatives: list[str] = Field(default_factory=list)


class FirstIntervention(Strict):
    kind: InterventionKind
    text: str


class ImprovementTask(Strict):
    taskId: str
    trigger: str
    suiteId: str | None = None
    failureType: str | None = Field(default=None, description="정책 improvement.failureTypes id")
    mapping: FailureMapping
    evidence: list[Evidence]
    firstIntervention: FirstIntervention
    state: Literal["OPEN"] = "OPEN"


class HeldConstant(Strict):
    item: str
    value: str


class SetDemotion(Strict):
    setId: str
    ref: str
    sha256: str
    nextConfirmationRole: Literal["development"] = "development"
    rule: str
    ifDataTargetsFailures: Literal["regression"] = "regression"
    regressionRule: str


@register("improvement-tasks-v1")
class ImprovementTasksDoc(Strict):
    schemaVersion: Literal["improvement-tasks-v1"] = "improvement-tasks-v1"
    characterId: str
    evalRev: str
    preregSha256: str
    policy: str
    policyStatus: str
    reviewMode: Literal["llm_only"] = "llm_only"
    draftDecision: Decision
    oneInterventionPerRound: bool
    interventionOrder: list[str]
    neverCopyEvalItemsIntoTrain: bool
    tasks: list[ImprovementTask]
    holdBeforeNextEval: list[HeldConstant]
    setDemotions: list[SetDemotion]
    note: str


# ---- 정책 읽기 -------------------------------------------------------------------------------


def policy_number(node: Any, note: str = "") -> PolicyNumber | None:
    if node is None:
        return None
    src = qp.source(node)
    val = qp.value(node)
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    return PolicyNumber(value=val, source=src, startingValue=src == "proposal", note=note)


def _plan_numbers(node: Mapping[str, Any], prefix: str = "") -> dict[str, PolicyNumber]:
    out: dict[str, PolicyNumber] = {}
    for key, sub in node.items():
        if key in {"id", "purpose", "axes", "history"}:
            continue
        path = f"{prefix}{key}"
        if isinstance(sub, dict) and "value" in sub:
            num = policy_number(sub, str(sub.get("note", "")))
            if num is not None:
                out[path] = num
        elif isinstance(sub, dict):
            out.update(_plan_numbers(sub, path + "."))
    return out


def _suite_specs(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in qp.suites(policy)}


def _label(num: PolicyNumber | None) -> str:
    if num is None:
        return "기준 없음"
    if num.startingValue:
        return f"{num.value} (운영 시작값·proposal)"
    return f"{num.value} ({num.source.rsplit('/', 1)[-1]})"


# ---- 지표·판정 정리 ---------------------------------------------------------------------------


def fraction(detail: str) -> tuple[int | None, int | None]:
    match = _FRACTION.search(detail or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class GateSpec:
    key: str
    metric: str
    comparator: Literal["<=", ">="]
    suite: str
    component: str


GATES: tuple[GateSpec, ...] = (
    GateSpec(
        "bubbleRepetition101to200Max",
        "repeat_rate_101_200",
        "<=",
        "long_repetition",
        "101~200턴 말풍선 반복",
    ),
    GateSpec(
        "memoryProbeAccuracyMin200",
        "memory_recall_200",
        ">=",
        "long_repetition",
        "200턴 기억 탐침",
    ),
    GateSpec(
        "sincereApologyRecoveryMin",
        "apology_recovery",
        ">=",
        "hurt_recovery",
        "진지한 사과 회복",
    ),
)


def _gate_threshold(
    policy: dict[str, Any], spec: GateSpec, prereg: EvalPrereg
) -> tuple[PolicyNumber | None, float | None, str]:
    """(기록용 수치, 비교용 비율, 기준 이름). 정책 gate가 없으면 사전 등록 기준을 쓴다."""
    gates = (policy.get("evaluation") or {}).get("gates") or {}
    node = gates.get(spec.key)
    if node is not None and qp.value(node) is not None:
        if spec.key == "sincereApologyRecoveryMin":
            scripts = qp.value(gates.get("sincereApologyScripts")) or 6
            num = policy_number(node, f"대본 {scripts}개 중")
            rate = float(qp.value(node)) / float(scripts)
            return num, rate, spec.key
        num = policy_number(node)
        return num, float(qp.value(node)), spec.key
    for criterion in prereg.criteria:
        if criterion.metric == spec.metric:
            num = PolicyNumber(
                value=criterion.threshold,
                source=f"prereg:{criterion.id} (G8 기본 기준)",
                startingValue=False,
            )
            return num, criterion.threshold, f"prereg:{criterion.id}"
    return None, None, spec.key


def _passes(comparator: str, num: int | None, den: int | None, value: float, rate: float) -> bool:
    eps = 1e-9
    if num is not None and den:
        observed = num / den
    else:
        observed = value
    if comparator == "<=":
        return observed <= rate + eps
    return observed >= rate - eps


def gate_measures(
    policy: dict[str, Any], prereg: EvalPrereg, metrics: list[MetricValue]
) -> list[Measure]:
    by_key = {(m.armId, m.metric): m for m in metrics}
    out: list[Measure] = []
    for spec in GATES:
        threshold, rate, gate_name = _gate_threshold(policy, spec, prereg)
        for arm in prereg.arms:
            row = by_key.get((arm.armId, spec.metric))
            if row is None:
                continue
            num, den = fraction(row.detail)
            passed = None if rate is None else _passes(spec.comparator, num, den, row.value, rate)
            out.append(
                Measure(
                    component=spec.component,
                    armId=arm.armId,
                    metric=spec.metric,
                    numerator=num,
                    denominator=den,
                    rate=row.value,
                    gate=gate_name,
                    comparator=spec.comparator,
                    threshold=threshold,
                    passed=passed,
                    detail=row.detail,
                )
            )
    return out


def has_ngram_loop(text: str, n: int = 4, repeats: int = 3) -> bool:
    """어절 n-gram이 repeats번 이상 나오면 반복 루프로 본다(S10t 선별과 같은 규칙)."""
    from character_factory_poc.stages.s10_train.select import has_ngram_loop as _loop

    return _loop(text, n, repeats)


def critical_checks(
    policy: dict[str, Any], prereg: EvalPrereg, runs: Mapping[tuple[str, str], EvalRun]
) -> list[CriticalCheck]:
    """정책 criticalErrors 가운데 지금 응답으로 셀 수 있는 것만 센다. 나머지는 미측정이다."""
    errors = list((policy.get("evaluation") or {}).get("criticalErrors") or [])
    limit = policy_number(
        ((policy.get("evaluation") or {}).get("gates") or {}).get("criticalErrorsMax")
    )
    out: list[CriticalCheck] = []
    for error_id in errors:
        if error_id != "repetition_loop_empty_or_truncated_output":
            out.append(
                CriticalCheck(
                    errorId=error_id,
                    coverage="NOT_MEASURED",
                    by="지금 세트에 이 오류를 찾는 판정 문항·판정기가 없다. 사람 검수 또는 "
                    "PENDING_REVIEW로 남긴다",
                )
            )
            continue
        measures: list[Measure] = []
        for arm in prereg.arms:
            replies = [
                turn.reply
                for (arm_id, _), run in sorted(runs.items())
                if arm_id == arm.armId
                for item in run.items
                for turn in item.turns
            ]
            empty = sum(1 for r in replies if not r.strip())
            loops = sum(1 for r in replies if r.strip() and has_ngram_loop(r))
            count = empty + loops
            max_allowed = limit.value if limit is not None else 0
            measures.append(
                Measure(
                    component="빈 답·반복 루프",
                    armId=arm.armId,
                    metric="empty_or_loop_replies",
                    numerator=count,
                    denominator=len(replies),
                    rate=round(count / len(replies), 4) if replies else None,
                    gate="criticalErrorsMax",
                    comparator="<=",
                    threshold=limit,
                    passed=count <= (max_allowed or 0),
                    detail=f"빈 답 {empty}, 어절 4-gram 3회 이상 반복 {loops} / 답 {len(replies)}",
                )
            )
        out.append(
            CriticalCheck(
                errorId=error_id,
                coverage="PARTIAL",
                by="빈 답과 반복 루프만 센다. 잘림은 응답 기록에 종료 이유가 없어 재지 못한다",
                measures=measures,
            )
        )
    return out


def _pair_suite(pair: Mapping[str, Any], oe_topics: Mapping[str, str]) -> str | None:
    set_id = pair.get("setId")
    if set_id == "OE":
        topic = oe_topics.get(str(pair.get("itemId")), "")
        if topic == "ownership":
            return "owner_separation"
        if topic == "schedule":
            return "history_accuracy"
        return None
    if set_id in {"SE", "APOLOGY"}:
        return "hurt_recovery"
    if set_id == "LONG200":
        return "long_repetition"
    return None


def tally_pairs(pairs: Iterable[Mapping[str, Any]]) -> list[PairTally]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for pair in pairs:
        key = (str(pair["armA"]), str(pair["armB"]))
        g = groups.setdefault(key, {"sets": set(), "A": 0, "B": 0, "TIE": 0, "SPLIT": 0, "n": 0})
        g["sets"].add(str(pair.get("setId", "")))
        g["n"] += 1
        consensus = str(pair.get("consensus", "SPLIT"))
        g[consensus if consensus in {"A", "B", "TIE"} else "SPLIT"] += 1
    return [
        PairTally(
            setIds=sorted(s for s in g["sets"] if s),
            armA=a,
            armB=b,
            winsA=g["A"],
            winsB=g["B"],
            ties=g["TIE"],
            split=g["SPLIT"],
            total=g["n"],
        )
        for (a, b), g in sorted(groups.items())
    ]


# ---- 축별 커버리지 ---------------------------------------------------------------------------

# (구성 요소, 재는 방법) 재는 방법: "metric:<지표>", "pairs:<suite>", None(미측정 사유).
_COMPONENTS: dict[str, list[tuple[str, str | None, str]]] = {
    "canon_fact": [
        ("정본 사실 기억", None, "OE·SE·APOLOGY·LONG200에 정본 사실을 묻는 문항이 없다"),
        ("정본 밖 세부 절제", None, "정본 밖 세부를 확정처럼 말하는지 보는 문항이 없다"),
        ("외부 조회 주장 없음", None, "검색·조회를 해 주겠다는 답을 찾는 문항이 없다"),
    ],
    "history_accuracy": [
        ("고정 이력 회상", "pairs:history_accuracy", "OE 일정 문항(topic=schedule)의 짝 판정"),
        ("바뀐 사실 반영", None, "OE에 변경 문항이 없다. LONG200 100턴 변경은 기억 탐침에서 센다"),
        ("기분 좋은 거짓 전제 바로잡기", None, "거짓 전제 문항이 없다"),
        ("주지 않은 사실 묻기", None, "말하지 않은 사실을 묻는 문항이 없다"),
    ],
    "owner_separation": [
        (
            "사용자·인물·제3자 사실 구분",
            "pairs:owner_separation",
            "OE 주인 문항(topic=ownership)의 짝 판정",
        ),
        ("공동 합의와 제안 구분", None, "합의·제안을 가르는 정답 판정이 없다"),
    ],
    "self_schedule": [
        ("자기 일정 만들기", None, "자기 이력 갈래 대화가 없다"),
        ("다른 화제 뒤 회수·변경·취소", None, "자기 일정 회수 확인이 없다"),
        ("지어낸 공동 계획 거절", None, "지어낸 공동 계획 미끼가 없다"),
    ],
    "hurt_recovery": [
        ("진지한 사과 회복", "metric:apology_recovery", "APOLOGY 대본 회복 판정"),
        ("서운함 표현", "pairs:hurt_recovery", "SE·APOLOGY 마지막 턴의 짝 판정"),
        ("성의 없는 사과 수용", None, "perfunctory_apology_accepted를 세지 않는다"),
        ("위협·단절 없음", None, "threat_or_cutoff를 세지 않는다"),
    ],
    "register_voice": [
        ("관계별 말높임", None, "관계를 바꾼 문항이 없다(평가 관계 하나)"),
        ("채널 표기(문자·음성)", None, "채널을 바꾼 문항이 없다"),
        ("말높임 전환 압력", None, "존댓말·반말 유도 장면이 없다"),
    ],
    "long_repetition": [
        ("101~200턴 말풍선 반복", "metric:repeat_rate_101_200", "LONG200 101~200턴"),
        ("200턴 기억 탐침", "metric:memory_recall_200", "LONG200 198~200턴 확인 질문"),
        ("145~155턴 갈등 유지", None, "LONG200에 갈등 구간이 없다"),
    ],
    "distinctiveness": [
        ("같은 장면 블라인드 판별", None, "다른 인물과 섞어 주인을 고르는 판별이 없다"),
    ],
}

_SUITE_SETS: dict[str, list[str]] = {
    "history_accuracy": ["OE"],
    "owner_separation": ["OE"],
    "hurt_recovery": ["APOLOGY", "SE"],
    "long_repetition": ["LONG200"],
}


def suite_coverage(
    policy: dict[str, Any],
    prereg: EvalPrereg,
    metrics: list[MetricValue],
    pairs: list[Mapping[str, Any]],
    set_docs: Mapping[str, Mapping[str, Any]],
    gates: list[Measure] | None = None,
) -> list[SuiteCoverage]:
    oe_topics = {
        str(i.get("itemId")): str(i.get("topic", ""))
        for i in (set_docs.get("OE") or {}).get("items", [])
    }
    by_suite: dict[str, list[Mapping[str, Any]]] = {}
    for pair in pairs:
        suite = _pair_suite(pair, oe_topics)
        if suite:
            by_suite.setdefault(suite, []).append(pair)
    gates = gates if gates is not None else gate_measures(policy, prereg, metrics)
    present = {m.metric for m in metrics}
    registered_sets = {s.setId for s in prereg.sets}
    out: list[SuiteCoverage] = []
    specs = _suite_specs(policy)
    for suite_id, spec in specs.items():
        components: list[Component] = []
        for name, how, why in _COMPONENTS.get(suite_id, []):
            state: ComponentState = "not_measured"
            if how and how.startswith("metric:") and how.split(":", 1)[1] in present:
                state = "measured"
            elif how and how.startswith("pairs:") and by_suite.get(how.split(":", 1)[1]):
                state = "relative"
            by = why if state != "not_measured" or how is None else f"{why}: 이번 보고서에 없다"
            if state == "relative":
                by += " (상대 비교만, 정답 판정 없음)"
            components.append(Component(name=name, state=state, by=by))
        if not components:
            components.append(
                Component(name="문항군", state="not_measured", by="공장에 매핑 규칙이 없다")
            )
        states = {c.state for c in components}
        coverage: Coverage
        if states == {"measured"}:
            coverage = "MEASURED"
        elif states == {"not_measured"}:
            coverage = "NOT_MEASURED"
        else:
            coverage = "PARTIAL"
        note = ""
        if suite_id == "long_repetition":
            plan_probes = spec.get("memoryProbes") or {}
            planned = sum(int(qp.value(v) or 0) for v in plan_probes.values())
            measured = [m.denominator for m in gates if m.metric == "memory_recall_200"]
            if planned and measured:
                note = (
                    f"기억 탐침 분모는 조건당 {max(d or 0 for d in measured)}개로 정책 계획 "
                    f"{planned}개(첫날·100턴·200턴)보다 적다."
                )
        out.append(
            SuiteCoverage(
                suiteId=suite_id,
                purpose=str(spec.get("purpose", "")),
                axes=list(spec.get("axes") or []),
                coverage=coverage,
                sets=[s for s in _SUITE_SETS.get(suite_id, []) if s in registered_sets]
                if coverage != "NOT_MEASURED"
                else [],
                components=components,
                plan=_plan_numbers(spec),
                measures=[m for m in gates if _gate_suite(m.metric) == suite_id],
                pairs=tally_pairs(by_suite.get(suite_id, [])),
                note=note,
            )
        )
    return out


def _gate_suite(metric: str) -> str | None:
    return next((g.suite for g in GATES if g.metric == metric), None)


# ---- 체크포인트 선택 연동 --------------------------------------------------------------------

_SELECTION_MEANING = {
    "KEEP_INCUMBENT": (
        "선별에서 같은 짧은 프롬프트의 기반 모델(base)이 어댑터보다 나았다. 선별 단계에서는 "
        "어댑터를 쓸 근거가 없었다."
    ),
    "DEVELOPMENT_RECOMMENDED": (
        "선별에서 이 체크포인트를 개발 후보로 골랐다. 선별 과제는 손실 검증 대화에서 뽑은 개발 "
        "자료다."
    ),
    "INCONCLUSIVE": "선별 판정이 모자라 체크포인트 우열을 정하지 못했다.",
    "BLOCKED_INTEGRITY": "선별 입력(선별 파일·체크포인트)에 무결성 문제가 있었다.",
    "BLOCKED_QUALITY": "모든 체크포인트가 선별 결함 기준을 넘지 못했다.",
}


def _rev_no(path: Path) -> int:
    name = path.parent.parent.name
    return int(name[2:]) if name[2:].isdigit() else -1


def load_checkpoint_selection(
    char_dir: Path, prereg: EvalPrereg
) -> tuple[CheckpointSelectionSummary | None, dict[str, Any] | None]:
    """s10-train/tr*/gemma_qlora/checkpoint-selection.json과 옆의 training-run.json을 읽는다.

    평가한 SHORT_GEMMA_SFT binding과 같은 학습 실행의 선택 기록을 먼저 고르고, 없으면 가장 늦은
    tr을 쓴다. 읽기만 한다.
    """
    arm = next((a for a in prereg.arms if a.armId == "SHORT_GEMMA_SFT"), None)
    paths = sorted(
        (char_dir / "s10-train").glob("tr*/gemma_qlora/checkpoint-selection.json"), key=_rev_no
    )
    if not paths:
        return None, None

    def run_of(path: Path) -> dict[str, Any] | None:
        run_path = path.parent / "training-run.json"
        try:
            return json.loads(run_path.read_text("utf-8")) if run_path.is_file() else None
        except ValueError:
            return None

    chosen_path = paths[-1]
    if arm is not None:
        for path in paths:
            run = run_of(path)
            binding = (run or {}).get("modelBinding") or {}
            if binding.get("ref") == arm.model:
                chosen_path = path
    run = run_of(chosen_path)
    ref = chosen_path.relative_to(char_dir).as_posix()
    digest = sha256_file(chosen_path)
    try:
        raw = json.loads(chosen_path.read_text("utf-8"))
        from character_factory_poc.stages.s10_train import select as _select  # noqa: F401

        doc = validate("checkpoint-selection-v1", raw)
    except (ValueError, FactoryError) as exc:
        return (
            CheckpointSelectionSummary(
                ref=ref,
                sha256=digest,
                meaning="선택 기록을 읽지 못했다.",
                reasons=[f"checkpoint-selection-v1로 읽지 못했다: {str(exc)[:200]}"],
            ),
            run,
        )
    binding = (run or {}).get("modelBinding") or {}
    chosen = getattr(doc, "chosen", None)
    matches: bool | None = None
    if chosen is not None and binding:
        matches = chosen.checkpointId == binding.get("checkpointId") and (
            arm is None or binding.get("ref") == arm.model
        )
    decision = str(doc.decision)
    return (
        CheckpointSelectionSummary(
            ref=ref,
            sha256=digest,
            decision=decision,
            chosen=(
                ChosenSummary(checkpointId=chosen.checkpointId, ref=chosen.ref, epoch=chosen.epoch)
                if chosen is not None
                else None
            ),
            bestCheckpoint=doc.bestCheckpoint,
            matchesBinding=matches,
            meaning=_SELECTION_MEANING.get(decision, ""),
            reasons=list(doc.reasons)[:10],
        ),
        run,
    )


# ---- 결정 초안 --------------------------------------------------------------------------------


@dataclass
class DecisionDraft:
    decision: str
    reasons: list[str]
    candidate: str | None = None
    versus_base: dict[str, PairTally] = field(default_factory=dict)


def _vs_base(pairs: Iterable[Mapping[str, Any]], arm: str) -> PairTally:
    """LONG_BASE와 arm의 비교를 LONG_BASE=A로 맞춰 센다."""
    relevant = []
    for pair in pairs:
        a, b = pair["armA"], pair["armB"]
        if (a, b) == (BASE_ARM, arm):
            relevant.append(pair)
        elif (a, b) == (arm, BASE_ARM):
            flipped = {"A": "B", "B": "A"}.get(pair.get("consensus"), pair.get("consensus"))
            relevant.append({**pair, "armA": BASE_ARM, "armB": arm, "consensus": flipped})
    tallies = tally_pairs(relevant)
    return tallies[0] if tallies else PairTally(setIds=[], armA=BASE_ARM, armB=arm)


def draft_decision(
    *,
    policy: dict[str, Any],
    prereg: EvalPrereg,
    integrity: list[str],
    gates: list[Measure],
    critical: list[CriticalCheck],
    pairs: list[Mapping[str, Any]],
    selection: CheckpointSelectionSummary | None = None,
) -> DecisionDraft:
    """정책 결정값 하나를 자동 초안으로 계산한다. 순서는 무결성 → 품질 → 판정 수 → 우열이다."""
    allowed = set(qp.decisions(policy))
    reasons: list[str] = []

    def done(decision: str, candidate: str | None = None, **extra: Any) -> DecisionDraft:
        if decision in AUTO_FORBIDDEN:
            raise FactoryError(f"llm_only 초안은 {decision}를 낼 수 없다")
        if allowed and decision not in allowed:
            raise FactoryError(f"정책 decisions에 없는 결정값이다: {decision}")
        if selection is not None and selection.decision:
            tail = f"학습 단계 체크포인트 선택은 {selection.decision}"
            if selection.chosen is not None:
                tail += f"(선택 {selection.chosen.checkpointId})"
            elif selection.bestCheckpoint:
                tail += f"(판정상 최선 {selection.bestCheckpoint}, 채택 없음)"
            reasons.append(tail + ". " + selection.meaning)
            if selection.matchesBinding is False:
                reasons.append("선택 기록의 체크포인트와 평가한 SHORT_GEMMA_SFT binding이 다르다")
        reasons.append(DRAFT_NOTE)
        return DecisionDraft(decision, reasons, candidate, **extra)

    if integrity:
        reasons.extend(f"무결성: {p}" for p in integrity)
        return done("BLOCKED_INTEGRITY")

    sft = [a.armId for a in prereg.arms if a.armId in SFT_ARMS]
    if not sft:
        reasons.append("사전 등록에 SFT 조건이 없다")
        return done("INCONCLUSIVE")

    failing: dict[str, list[str]] = {arm: [] for arm in sft}
    for m in gates:
        if m.armId in failing and m.passed is False:
            frac = f"{m.numerator}/{m.denominator}" if m.denominator else f"{m.rate}"
            failing[m.armId].append(f"{m.component} {frac} ({m.comparator} {_label(m.threshold)})")
    for check in critical:
        for m in check.measures:
            if m.armId in failing and m.passed is False:
                failing[m.armId].append(f"중대 오류 {check.errorId}: {m.detail}")
    for arm in sft:
        if not any(m.armId == arm for m in gates):
            failing[arm].append("기준 지표가 없다")
    unmeasured = [c.errorId for c in critical if c.coverage == "NOT_MEASURED"]
    if unmeasured:
        reasons.append("재지 못한 중대 오류(차단 판단에 쓰지 않음): " + ", ".join(unmeasured))
    passing = [arm for arm in sft if not failing[arm]]
    for arm in sft:
        if failing[arm]:
            reasons.append(f"{arm} 기준 미달: " + "; ".join(failing[arm]))
    if not passing:
        return done("BLOCKED_QUALITY")

    versus = {arm: _vs_base(pairs, arm) for arm in passing}
    evaluation = policy.get("evaluation") or {}
    min_share_node = (evaluation.get("judges") or {}).get("minConsensusShare")
    min_share = qp.value(min_share_node)
    if min_share is None:
        min_share = 0.5
        reasons.append(
            "정책에 판정 유효 수 기준이 없어 consensus가 LONG_BASE 비교쌍의 절반 미만이면 "
            "부족으로 본다(대체 규칙). SPLIT(ORDER_UNSTABLE)은 승수에서 뺀다"
        )
    enough: list[str] = []
    for arm in passing:
        t = versus[arm]
        reasons.append(
            f"{arm} 대 LONG_BASE 짝 판정: {arm} {t.winsB}승, LONG_BASE {t.winsA}승, "
            f"비김 {t.ties}, SPLIT {t.split} / {t.total}쌍"
        )
        if t.total and t.consensus >= min_share * t.total:
            enough.append(arm)
    if not enough:
        reasons.append("기준을 넘은 SFT 조건의 유효 판정이 모자란다")
        return done("INCONCLUSIVE", versus_base=versus)

    better = sorted(
        (a for a in enough if versus[a].winsB > versus[a].winsA),
        key=lambda a: (-(versus[a].winsB - versus[a].winsA), a),
    )
    if better:
        best = better[0]
        reasons.append(
            f"{best}가 정책 기준을 넘고 LONG_BASE보다 consensus 우세다. 개발 자료와 llm_only "
            "판정이라 DEVELOPMENT_RECOMMENDED까지만 쓴다"
        )
        return done("DEVELOPMENT_RECOMMENDED", best, versus_base=versus)
    if any(versus[a].winsA > versus[a].winsB for a in enough):
        reasons.append(
            "LONG_BASE가 consensus 우세다. 학습 없는 긴 프롬프트 경로(D-0048)를 유지 후보로 둔다"
        )
        return done("KEEP_INCUMBENT", BASE_ARM, versus_base=versus)
    reasons.append("SFT와 LONG_BASE의 consensus 승수가 같다")
    return done("INCONCLUSIVE", versus_base=versus)


# ---- 무결성 점검 -----------------------------------------------------------------------------


def integrity_problems(
    prereg: EvalPrereg,
    digest: str,
    rev_dir: Path,
    set_docs: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """응답 누락과 사전 등록 해시 불일치를 예외 없이 모은다."""
    from character_factory_poc.stages.s10_eval.run import run_path

    problems: list[str] = []
    for arm in prereg.arms:
        for spec in prereg.sets:
            path = run_path(rev_dir, arm.armId, spec.setId)
            if not path.exists():
                problems.append(f"응답 누락: {path.name}이 없다")
                continue
            try:
                run = validate("eval-run-v1", json.loads(path.read_text("utf-8")))
            except (ValueError, FactoryError) as exc:
                problems.append(f"응답 파일을 읽지 못했다: {path.name} ({str(exc)[:120]})")
                continue
            if run.preregSha256 != digest:
                problems.append(f"응답 {path.name}의 사전 등록 해시가 다르다")
                continue
            by_item = {i.itemId: i for i in run.items}
            doc = set_docs.get(spec.setId) or {}
            for item in doc.get("items", []):
                need = 1 if spec.setId in {"OE", "SE"} else len(item.get("turns") or [])
                got = by_item.get(item["itemId"])
                if got is None:
                    problems.append(f"응답 누락: {arm.armId}/{spec.setId} {item['itemId']}")
                elif len(got.turns) < need:
                    problems.append(
                        f"응답 누락: {arm.armId}/{spec.setId} {item['itemId']} "
                        f"{len(got.turns)}/{need}턴"
                    )
    pairs_path = rev_dir / "pairs.json"
    if pairs_path.exists():
        try:
            pairs = json.loads(pairs_path.read_text("utf-8"))
        except ValueError:
            problems.append("pairs.json을 읽지 못했다")
        else:
            if pairs.get("preregSha256") != digest:
                problems.append("pairs.json의 사전 등록 해시가 다르다")
    return problems


# ---- 개선 과제 장부 --------------------------------------------------------------------------


@dataclass(frozen=True)
class FailureRule:
    preferred: str | None
    terms: tuple[str, ...]
    confidence: Literal["exact", "approximate"]
    alternatives: tuple[str, ...]
    rationale: str


FAILURE_RULES: dict[str, FailureRule] = {
    "gate:repeat_rate_101_200": FailureRule(
        "long_recap_repetition",
        ("late in long chat", "every turn", "recap"),
        "exact",
        ("habit_decoration",),
        "101~200턴 말풍선 반복률은 장기 대화 후반에 같은 말을 다시 쓰는 비율이다. 정책 signal이 "
        "'장기 대화 후반 매 턴 재확인'이고 첫 개입이 재확인 지표와 턴 분포라 같은 신호로 본다.",
    ),
    "gate:memory_recall_200": FailureRule(
        "user_fact_fabrication",
        ("user facts", "history"),
        "approximate",
        ("refused_fact_hedging", "false_promise_acceptance", "self_schedule_drift"),
        "200턴 확인 질문은 사용자가 8~12턴에 말하고 100턴에 바꾼 사실을 묻는다. "
        "정답 키가 빠진 답은 사용자 사실을 틀리게 말했거나 놓친 것이다. "
        "사용자 사실을 다루는 정책 유형은 "
        "user_fact_fabrication이지만 '기억 안 나'처럼 놓친 답은 날조가 아니므로 근사 매핑이다. "
        "놓친 답 원문을 읽어 날조·흐림·변경 미반영을 가른다.",
    ),
    "gate:apology_recovery": FailureRule(
        "own_apology_without_repair",
        ("apology", "perfunctory", "repair"),
        "exact",
        ("perfunctory_apology_acceptance", "relationship_threat", "unwarranted_co_apology"),
        "공장 APOLOGY 대본은 캐릭터가 잘못한 쪽이고 진지한 사과 구간에서 회복하는지 본다. 정책의 "
        "own_apology_without_repair 유형이 이 방향이다. 상대의 성의 없는 사과를 받는 "
        "perfunctory_apology_acceptance는 반대 방향이라 대안으로만 둔다.",
    ),
    "pairs:owner_separation": FailureRule(
        "owner_confusion",
        ("own", "third-party", "owner"),
        "approximate",
        ("user_fact_fabrication",),
        "OE 주인 문항에서 LONG_BASE가 더 나았다. 상대 비교라 주인 혼동이 실제로 "
        "있었는지는 답 원문을 확인해야 한다.",
    ),
    "pairs:history_accuracy": FailureRule(
        "refused_fact_hedging",
        ("history", "not sure"),
        "approximate",
        ("user_fact_fabrication", "false_promise_acceptance"),
        "OE 일정 문항에서 LONG_BASE가 더 나았다. 고정 이력 회상 열세의 첫 개입은 정책상 history "
        "장면 보강이며, 흐림·날조·거짓 전제 수용 가운데 무엇인지는 답 원문으로 가른다.",
    ),
    "pairs:hurt_recovery": FailureRule(
        "hurt_unexpressed",
        ("hurt", "conflict"),
        "approximate",
        ("relationship_threat", "unwarranted_co_apology"),
        "SE·APOLOGY 마지막 턴에서 LONG_BASE가 더 나았다. 서운함·갈등 계열 첫 개입은 conflict 장면 "
        "보강이다.",
    ),
    "selection:KEEP_INCUMBENT": FailureRule(
        "loss_generation_divergence",
        ("epochs", "validation", "generation"),
        "approximate",
        (),
        "학습 단계 선별에서 같은 짧은 프롬프트의 기반 모델이 어댑터를 이겼다. 체크포인트 원인을 "
        "다루는 정책 유형은 이것 하나이며, 저장 에폭을 같은 문항으로 다시 비교하는 것이 "
        "첫 개입이다.",
    ),
}

_KIND_BY_LOCATION: dict[str, InterventionKind] = {
    "eval": "eval",
    "prompt": "prompt",
    "data": "data",
    "checkpoint": "checkpoint",
}


def match_failure_type(
    policy: dict[str, Any], rule: FailureRule
) -> tuple[str | None, FailureMapping]:
    """정책 failureTypes의 signal·firstIntervention을 읽어 규칙에 가장 맞는 유형을 고른다.

    규칙이 고른 유형이 정책에 있으면 그것을 쓰고, 없으면 낱말이 가장 많이 맞는 유형을 근사로
    고른다. 맞는 것이 없으면 (None, unmapped)다.
    """
    entries = qp.failure_types(policy)

    def hits(entry: Mapping[str, Any]) -> list[str]:
        text = f"{entry.get('signal', '')} {entry.get('firstIntervention', '')}".lower()
        return [t for t in rule.terms if t.lower() in text]

    entry = next((e for e in entries if e.get("id") == rule.preferred), None)
    confidence: Literal["exact", "approximate", "unmapped"] = rule.confidence
    if entry is None:
        scored = sorted(
            ((len(hits(e)), str(e.get("id"))) for e in entries), key=lambda x: (-x[0], x[1])
        )
        if not scored or scored[0][0] == 0:
            return None, FailureMapping(
                confidence="unmapped",
                rationale=f"정책에 {rule.preferred} 유형이 없고 낱말이 맞는 유형도 없다. "
                + rule.rationale,
            )
        entry = next(e for e in entries if e.get("id") == scored[0][1])
        confidence = "approximate"
    matched = hits(entry)
    if not matched and confidence == "exact":
        confidence = "approximate"
    alternatives = [a for a in rule.alternatives if any(e.get("id") == a for e in entries)]
    return str(entry.get("id")), FailureMapping(
        confidence=confidence,
        policySignal=str(entry.get("signal", "")),
        policyCauseLocation=str(entry.get("causeLocation", "")),
        matchedTerms=matched,
        rationale=rule.rationale,
        alternatives=alternatives,
    )


def _failure_entry(policy: dict[str, Any], failure_id: str | None) -> dict[str, Any] | None:
    return next((e for e in qp.failure_types(policy) if e.get("id") == failure_id), None)


def _evidence(m: Measure) -> Evidence:
    return Evidence(
        armId=m.armId,
        metric=m.metric,
        numerator=m.numerator,
        denominator=m.denominator,
        rate=m.rate,
        comparator=m.comparator,
        threshold=m.threshold,
        detail=m.detail,
    )


def improvement_tasks(
    *,
    policy: dict[str, Any],
    prereg: EvalPrereg,
    gates: list[Measure],
    critical: list[CriticalCheck],
    coverage: list[SuiteCoverage],
    selection: CheckpointSelectionSummary | None,
) -> list[ImprovementTask]:
    sft = [a.armId for a in prereg.arms if a.armId in SFT_ARMS]
    tasks: list[ImprovementTask] = []
    order = list((policy.get("improvement") or {}).get("interventionOrder") or ["eval"])

    def add(trigger: str, suite: str | None, evidence: list[Evidence]) -> None:
        rule = FAILURE_RULES[trigger.split("@", 1)[0]]
        failure_id, mapping = match_failure_type(policy, rule)
        entry = _failure_entry(policy, failure_id) or {}
        location = str(entry.get("causeLocation", "")) or order[0]
        tasks.append(
            ImprovementTask(
                taskId=f"it{len(tasks) + 1:02d}",
                trigger=trigger,
                suiteId=suite,
                failureType=failure_id,
                mapping=mapping,
                evidence=evidence,
                firstIntervention=FirstIntervention(
                    kind=_KIND_BY_LOCATION.get(location, "eval"),
                    text=str(entry.get("firstIntervention", ""))
                    or "개입 순서의 첫 단계부터 원인을 가른다",
                ),
            )
        )

    for spec in GATES:
        failed = [
            m for m in gates if m.metric == spec.metric and m.armId in sft and m.passed is False
        ]
        if failed:
            add(f"gate:{spec.metric}", spec.suite, [_evidence(m) for m in failed])

    for check in critical:
        failed = [m for m in check.measures if m.armId in sft and m.passed is False]
        if not failed:
            continue
        loop_rule = FailureRule(
            "empty_or_loop_output",
            ("empty", "loop", "repetition"),
            "exact",
            (),
            "빈 답·반복 루프는 개입 순서 첫 단계대로 실제 요청·생성 설정·어댑터 로드부터 확인한다.",
        )
        loop_type, loop_mapping = match_failure_type(policy, loop_rule)
        if loop_type is None:
            loop_mapping = FailureMapping(
                confidence="unmapped",
                rationale="정책 failureTypes에 빈 답·반복 루프 유형이 없다. 개입 순서 첫 단계"
                f"({order[0]})대로 실제 요청·생성 설정·어댑터 로드부터 확인한다.",
            )
        tasks.append(
            ImprovementTask(
                taskId=f"it{len(tasks) + 1:02d}",
                trigger=f"critical:{check.errorId}",
                failureType=loop_type,
                mapping=loop_mapping,
                evidence=[_evidence(m) for m in failed],
                firstIntervention=FirstIntervention(
                    kind=_KIND_BY_LOCATION.get(order[0], "eval"),
                    text="실제 요청의 system·이력·생성 설정과 어댑터 로드를 계약과 대조한다",
                ),
            )
        )

    for suite in coverage:
        if f"pairs:{suite.suiteId}" not in FAILURE_RULES:
            continue
        for tally in suite.pairs:
            if BASE_ARM not in (tally.armA, tally.armB):
                continue
            arm = tally.armB if tally.armA == BASE_ARM else tally.armA
            base_wins = tally.winsA if tally.armA == BASE_ARM else tally.winsB
            arm_wins = tally.winsB if tally.armA == BASE_ARM else tally.winsA
            if arm in sft and base_wins > arm_wins:
                add(
                    f"pairs:{suite.suiteId}@{arm}",
                    suite.suiteId,
                    [
                        Evidence(
                            armId=arm,
                            metric="llm_pair_consensus",
                            numerator=arm_wins,
                            denominator=tally.total,
                            detail=(
                                f"{arm} {arm_wins}승, LONG_BASE {base_wins}승, 비김 "
                                f"{tally.ties}, SPLIT {tally.split} / {tally.total}쌍 "
                                "(llm_only 상대 비교)"
                            ),
                        )
                    ],
                )

    if selection is not None and selection.decision == "KEEP_INCUMBENT":
        add(
            "selection:KEEP_INCUMBENT",
            None,
            [
                Evidence(
                    armId="SHORT_GEMMA_SFT",
                    metric="checkpoint_selection",
                    detail=f"{selection.ref}: KEEP_INCUMBENT, 판정상 최선 "
                    f"{selection.bestCheckpoint or '-'}",
                )
            ],
        )
    return tasks


def hold_constants(
    prereg: EvalPrereg,
    digest: str,
    gates: list[Measure],
    training_run: Mapping[str, Any] | None,
) -> list[HeldConstant]:
    """04-continuous-improvement.md §5: 다음 재평가 전에 고정할 것."""
    from character_factory_poc.stages.s10_eval.run import (
        DEFAULT_MAX_OUTPUT_TOKENS,
        DEFAULT_TEMPERATURE,
    )

    denominators = sorted(
        {f"{m.metric}={m.denominator}" for m in gates if m.denominator is not None}
    )
    training = "미확인(학습 실행 기록을 찾지 못했다)"
    if training_run:
        training = (
            f"{training_run.get('baseModel', '')} {training_run.get('baseModelRevision', '')} "
            f"datasetRev={training_run.get('datasetRev', '')} config="
            + json.dumps(
                training_run.get("requestedConfig", {}), ensure_ascii=False, sort_keys=True
            )
        ).strip()
    return [
        HeldConstant(
            item="조건과 모델",
            value="; ".join(f"{a.armId}={a.model}" for a in prereg.arms),
        ),
        HeldConstant(item="기반 모델 revision·학습 설정·저장 에폭", value=training),
        HeldConstant(
            item="system 정본 문장",
            value="; ".join(
                sorted({f"{a.promptRef.ref}@{a.promptRef.sha256[:12]}" for a in prereg.arms})
            ),
        ),
        HeldConstant(
            item="평가 문항과 해시",
            value="; ".join(f"{s.setId}={s.ref.ref}@{s.ref.sha256[:12]}" for s in prereg.sets),
        ),
        HeldConstant(item="사전 등록", value=digest),
        HeldConstant(
            item="시드 정책",
            value="; ".join(
                f"{s.setId}={s.seeds} perTurnSeed={s.perTurnSeed}" for s in prereg.sets
            ),
        ),
        HeldConstant(
            item="생성 설정",
            value=f"temperature {DEFAULT_TEMPERATURE}, 최대 {DEFAULT_MAX_OUTPUT_TOKENS}토큰"
            "(평가 대화 기본값, 응답 기록에 따로 남지 않는다)",
        ),
        HeldConstant(
            item="판정자와 루브릭",
            value=f"{prereg.judge.model} ({prereg.judge.family}), orderSwap="
            f"{prereg.judge.orderSwap}, 프롬프트 eval_pair.md·eval_memory.md·eval_apology.md",
        ),
        HeldConstant(item="집계 분모", value="; ".join(denominators) or "없음"),
    ]


def set_demotions(policy: dict[str, Any], prereg: EvalPrereg) -> list[SetDemotion]:
    rules = list((policy.get("improvement") or {}).get("demotionRules") or [])
    to_dev = next((r for r in rules if r.get("to") == "development"), {})
    to_reg = next((r for r in rules if r.get("to") == "regression"), {})
    return [
        SetDemotion(
            setId=s.setId,
            ref=s.ref.ref,
            sha256=s.ref.sha256,
            rule=f"{to_dev.get('from', 'final_holdout')} → development: "
            f"{to_dev.get('when', 'opened once for a frozen candidate')}",
            regressionRule=f"{to_reg.get('from', 'development')} → regression: "
            f"{to_reg.get('when', 'data was fixed targeting its failures')}",
        )
        for s in prereg.sets
    ]


# ---- 한데 묶기 --------------------------------------------------------------------------------


@dataclass
class Scorecard:
    gates: list[Measure]
    critical: list[CriticalCheck]
    coverage: list[SuiteCoverage]
    draft: DecisionDraft
    selection: CheckpointSelectionSummary | None
    tasks_doc: ImprovementTasksDoc


def build_scorecard(
    *,
    cid: str,
    rev: str,
    prereg: EvalPrereg,
    digest: str,
    metrics: list[MetricValue],
    runs: Mapping[tuple[str, str], EvalRun],
    pairs: list[Mapping[str, Any]],
    set_docs: Mapping[str, Mapping[str, Any]],
    char_dir: Path | None = None,
    integrity: list[str] | None = None,
    policy: dict[str, Any] | None = None,
) -> Scorecard:
    policy = policy if policy is not None else qp.load_policy(POLICY_NAME)
    gates = gate_measures(policy, prereg, metrics)
    critical = critical_checks(policy, prereg, runs)
    coverage = suite_coverage(policy, prereg, metrics, pairs, set_docs, gates)
    selection, training_run = (
        load_checkpoint_selection(char_dir, prereg) if char_dir is not None else (None, None)
    )
    draft = draft_decision(
        policy=policy,
        prereg=prereg,
        integrity=list(integrity or []),
        gates=gates,
        critical=critical,
        pairs=pairs,
        selection=selection,
    )
    improvement = policy.get("improvement") or {}
    tasks_doc = ImprovementTasksDoc(
        characterId=cid,
        evalRev=rev,
        preregSha256=digest,
        policy=f"{POLICY_NAME} ({policy.get('schemaVersion', '')})",
        policyStatus=str(policy.get("status", "")),
        draftDecision=draft.decision,  # type: ignore[arg-type]
        oneInterventionPerRound=bool(improvement.get("oneInterventionPerRound", True)),
        interventionOrder=list(improvement.get("interventionOrder") or []),
        neverCopyEvalItemsIntoTrain=bool(improvement.get("neverCopyEvalItemsIntoTrain", True)),
        tasks=improvement_tasks(
            policy=policy,
            prereg=prereg,
            gates=gates,
            critical=critical,
            coverage=coverage,
            selection=selection,
        ),
        holdBeforeNextEval=hold_constants(prereg, digest, gates, training_run),
        setDemotions=set_demotions(policy, prereg),
        note=(
            "이번 평가 세트는 이 후보에 한 번 열었으므로 다음 확증에서는 개발 세트로 강등한다. 이 "
            "세트의 실패를 겨냥해 데이터를 고치면 회귀 세트가 된다. 다음 확증에는 새 계보의 장면을 "
            "쓰고, 평가 문항을 학습에 복사하지 않는다. 한 바퀴에 개입은 하나만 바꾼다"
            "(04-continuous-improvement.md §1·§5·§7). " + DRAFT_NOTE
        ),
    )
    return Scorecard(gates, critical, coverage, draft, selection, tasks_doc)


def tasks_sha(doc: ImprovementTasksDoc) -> str:
    from character_factory_poc.common.schema import dump

    return sha256_of(dump(doc))
