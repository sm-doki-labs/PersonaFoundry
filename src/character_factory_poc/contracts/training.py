"""S10 학습·평가 계약 (LLD §5.15, D-0044·D-0045).

학습은 두 환경(Gemma 4 31B QLoRA 임대 GPU, Vertex Gemini 튜닝)이고 PoC에서는 dry run까지다(P-24).
평가는 사전 등록 → 조건별 응답 수집 → 지표 계산 + LLM 짝 판정 + 사람 20쌍 → G8.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import ArtifactRef, Strict

TrainingProvider = Literal["gemma_qlora", "vertex_gemini", "fake"]
RunStatus = Literal["PLANNED", "SUBMITTED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
ArmId = Literal["LONG_BASE", "SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT"]
SetId = Literal["OE", "SE", "APOLOGY", "LONG200"]


class CostEstimate(Strict):
    usd: float | None = None
    gpuHours: float | None = None
    billableTokens: int | None = None
    basis: str = Field(default="", description="단가 출처와 확인 날짜")


class Transfer(Strict):
    """임대 GPU로 보낸 파일. 원격 해시가 맞아야 학습을 시작한다."""

    path: str
    bytes: int
    sha256: str
    remoteSha256: str | None = None


class Checkpoint(Strict):
    checkpointId: str
    epoch: int | float | None = Field(
        default=None, description="공급자가 보고한 원값. Gemma는 0.5 epoch 단위(D-0077)"
    )
    step: int | None = None
    ref: str = Field(description="어댑터 파일 경로 또는 공급자 체크포인트 이름")
    validationLoss: float | None = Field(
        default=None, description="기록용. 체크포인트 선택은 생성 결과로 한다(D-0077)"
    )


class ModelBinding(Strict):
    provider: TrainingProvider
    ref: str
    checkpointId: str


@register("training-run-v2")
class TrainingRun(Strict):
    schemaVersion: Literal["training-run-v2"] = "training-run-v2"
    characterId: str
    datasetRev: str
    datasetDigest: str
    provider: TrainingProvider
    baseModel: str
    baseModelRevision: str = ""
    requestedConfig: dict[str, Any]
    appliedConfig: dict[str, Any] = Field(
        default_factory=dict, description="공급자가 돌려준 실제 값"
    )
    dryRun: bool = Field(description="True면 호출 계획과 비용 추정만 있고 jobId가 없다")
    estimate: CostEstimate
    budgetUsd: float
    status: RunStatus
    jobId: str | None = None
    transfers: list[Transfer] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    modelBinding: ModelBinding | None = None


class Arm(Strict):
    armId: ArmId
    promptRef: ArtifactRef = Field(description="긴 프롬프트 또는 짧은 system")
    model: str = Field(description="LONG_BASE는 현행 서비스 모델, SFT는 model_binding ref")


class EvalSet(Strict):
    setId: SetId
    ref: ArtifactRef
    seeds: list[int] = Field(min_length=1)
    perTurnSeed: bool = Field(description="연속 대화는 턴마다 다른 시드(가이드 §10)")
    personas: int = Field(default=1, ge=1, description="LONG200은 사용자 페르소나 4명")


class JudgeSpec(Strict):
    model: str
    family: str = Field(description="생성 모델과 다른 계열이어야 한다(D-0010)")
    orderSwap: bool = True


class Criterion(Strict):
    id: str
    metric: Literal["repeat_rate_101_200", "memory_recall_200", "apology_recovery"]
    comparator: Literal["<=", ">="]
    threshold: float
    appliesTo: Literal["SFT_ANY", "EACH_ARM"] = "SFT_ANY"


@register("eval-prereg-v2")
class EvalPrereg(Strict):
    """학습 전에 고정한다. sha256이 다르면 분석을 거절한다(D-0006)."""

    schemaVersion: Literal["eval-prereg-v2"] = "eval-prereg-v2"
    characterId: str
    personaVersion: str
    arms: list[Arm] = Field(min_length=2)
    sets: list[EvalSet] = Field(min_length=1)
    judge: JudgeSpec
    humanPairs: int = Field(default=20, ge=0)
    criteria: list[Criterion]
    frozenAt: str


class Turn(Strict):
    user: str
    reply: str
    seed: int | None = None


class EvalItem(Strict):
    itemId: str
    personaId: str = ""
    turns: list[Turn]


@register("eval-run-v1")
class EvalRun(Strict):
    """한 조건·한 평가 세트의 응답 모음."""

    schemaVersion: Literal["eval-run-v1"] = "eval-run-v1"
    characterId: str
    preregSha256: str
    armId: ArmId
    setId: SetId
    model: str
    items: list[EvalItem]


class MetricValue(Strict):
    armId: ArmId
    metric: str
    value: float
    detail: str = ""


class CriterionResult(Strict):
    id: str
    armId: ArmId
    value: float
    passed: bool


class PairVerdict(Strict):
    pairId: str
    armA: ArmId
    armB: ArmId
    forward: Literal["A", "B", "TIE"]
    reverse: Literal["A", "B", "TIE"]
    consensus: Literal["A", "B", "TIE", "SPLIT"]


class HumanPick(Strict):
    pairId: str
    pick: Literal["A", "B", "TIE"]


@register("eval-report-v2")
class EvalReport(Strict):
    schemaVersion: Literal["eval-report-v2"] = "eval-report-v2"
    characterId: str
    preregSha256: str
    runRefs: list[ArtifactRef]
    metrics: list[MetricValue]
    criteriaResults: list[CriterionResult]
    llmPairs: list[PairVerdict]
    humanPicks: list[HumanPick] = Field(default_factory=list)
    llmHumanAgreement: float | None = None
    recommendation: str = Field(description="G8 참고용. 결정은 사람이 한다")
    # D-0078 정책 점수표(s10_eval/scorecard.py). 없으면 이전 보고서와 같다.
    decision: (
        Literal[
            "RELEASE_ACCEPTED",
            "MODEL_ACCEPTED",
            "DEVELOPMENT_RECOMMENDED",
            "KEEP_INCUMBENT",
            "INCONCLUSIVE",
            "BLOCKED_INTEGRITY",
            "BLOCKED_QUALITY",
        ]
        | None
    ) = Field(default=None, description="정책 결정값 자동 초안. G8 사람 결정을 대신하지 않는다")
    decisionReasons: list[str] = Field(default_factory=list)
    suiteCoverage: list[dict[str, Any]] = Field(
        default_factory=list, description="정책 suite별 커버리지(scorecard SuiteCoverage)"
    )
    criticalErrorChecks: list[dict[str, Any]] = Field(
        default_factory=list, description="정책 criticalErrors별 측정 여부(scorecard CriticalCheck)"
    )
    checkpointSelection: dict[str, Any] | None = Field(
        default=None, description="s10-train의 checkpoint-selection.json 요약"
    )
    improvementTasksRef: ArtifactRef | None = None
