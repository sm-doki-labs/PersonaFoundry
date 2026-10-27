"""S9 데이터셋 계약 (LLD §5.14, D-0044·D-0045).

학습 가이드(한소민 QLoRA 데이터셋·프롬프트 구축 가이드)의 절차를 계약으로 옮긴다:
클러스터별 인계안 → 12개 샘플 → G7a 사람 검토 → 대량 작성 → 기계 검사 → G7.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import ArtifactRef, Strict

ClusterId = Literal["base", "situation", "history", "ownership", "conflict"]
Material = Literal["SNS_REWRITE", "SYNTH", "NIKL"]
Split = Literal["train", "validation_base", "validation_augmented", "eval"]
Verdict = Literal["ADOPT", "FIX", "REJECT"]


class ClusterPlan(Strict):
    clusterId: ClusterId
    label: str = Field(description="예: 말투·관계·일상 기반")
    share: float = Field(ge=0, le=1, description="학습 대화 수 기준 비율")
    targetConversations: int = Field(ge=0)
    materials: list[Material]
    sampleSize: int = Field(default=12, ge=1, description="G7a에 올리는 샘플 수")


class ValidationPlan(Strict):
    baseConversations: int = Field(default=60, ge=0)
    augmentedShare: float = Field(default=0.1, ge=0, le=1, description="보강 클러스터별 검증 비율")


@register("data-plan-v1")
class DataPlan(Strict):
    """S9 계획. 설정의 기본값은 학습 가이드 §6의 소민 기준 배합이다(D-0045 (2))."""

    schemaVersion: Literal["data-plan-v1"] = "data-plan-v1"
    characterId: str
    personaVersion: str
    promptPairSha256: str = Field(description="짧은 system의 출처가 되는 prompt-pair-v1")
    targetTrainConversations: int = Field(ge=1)
    clusters: list[ClusterPlan]
    validation: ValidationPlan = Field(default_factory=ValidationPlan)
    guideRef: str = Field(description="학습 가이드 경로와 확인 날짜")
    writerModel: str
    judgeModel: str = ""


class BehaviorRow(Strict):
    """성격은 형용사가 아니라 상황 → 먼저 보는 것 → 고르는 행동 → 말투로 쓴다(가이드 §4)."""

    situation: str
    attention: str
    choice: str
    voice: str


@register("data-handoff-v1")
class DataHandoff(Strict):
    """클러스터별 인계안. 작문 모델에 보내기 전에 G7a에서 샘플과 함께 사람이 본다."""

    schemaVersion: Literal["data-handoff-v1"] = "data-handoff-v1"
    characterId: str
    planSha256: str
    clusterId: ClusterId
    behaviorTable: list[BehaviorRow]
    voiceExamples: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    notes: str = ""


class Message(Strict):
    role: Literal["user", "assistant"]
    content: str


class ConversationChecks(Strict):
    """결정 검사 결과. 차단(blocking) 항목이 하나라도 False면 데이터셋에 넣지 않는다."""

    blocking: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class Provenance(Strict):
    writerModel: str
    requestRef: str = Field(description="원장의 callId 또는 요청 파일 경로")
    sourceRef: str = Field(default="", description="SNS 재작성이면 원본 대화 ID")
    editedBy: Literal["model", "human", "none"] = "none"


@register("conversation-v1")
class Conversation(Strict):
    """학습 예시 한 개. 입력 형식은 짧은 system + 실제 대화 이력, 프리필 없음(가이드 §1)."""

    schemaVersion: Literal["conversation-v1"] = "conversation-v1"
    conversationId: str
    clusterId: ClusterId
    material: Material
    skeletonId: str = Field(description="분할을 묶는 단위. 같은 뼈대는 같은 분할로 간다")
    system: str
    messages: list[Message] = Field(min_length=2)
    checks: ConversationChecks = Field(default_factory=ConversationChecks)
    provenance: Provenance


@register("data-sample-v1")
class DataSample(Strict):
    """G7a에 올리는 클러스터별 샘플 묶음."""

    schemaVersion: Literal["data-sample-v1"] = "data-sample-v1"
    characterId: str
    planSha256: str
    clusterId: ClusterId
    handoffSha256: str
    conversations: list[ArtifactRef]


class ClusterCount(Strict):
    conversations: int
    replies: int
    supervisedTokens: int | None = Field(
        default=None, description="학습 템플릿으로 잰 값. 못 쟀으면 None"
    )


class SplitFile(Strict):
    split: Split
    path: str
    sha256: str
    conversations: int


@register("dataset-rev-v2")
class DatasetRev(Strict):
    """G7에서 고정되는 데이터셋 revision. 고정 뒤에는 고치지 않고 새 revision을 만든다."""

    schemaVersion: Literal["dataset-rev-v2"] = "dataset-rev-v2"
    characterId: str
    datasetRev: str = Field(pattern=r"^ds\d+$")
    personaVersion: str
    planSha256: str
    sampleQaRefs: list[str] = Field(description="G7a data-qa-v2 기록들")
    clusterCounts: dict[str, ClusterCount]
    files: list[SplitFile]
    blockingFailures: int = Field(ge=0, description="기계 검사 차단 실패 수. 0이어야 G7에 올린다")
    warnings: int = Field(default=0, ge=0)
    digest: str = Field(description="예시를 conversationId로 정렬한 정규화 JSON의 sha256")


@register("data-qa-v2")
class DataQa(Strict):
    """G7a(샘플)·G7(최종 표본) 사람 판정."""

    schemaVersion: Literal["data-qa-v2"] = "data-qa-v2"
    characterId: str
    gate: Literal["G7a", "G7"]
    subjectSha256: str = Field(description="data-sample-v1 또는 dataset-rev-v2의 sha256")
    verdicts: dict[str, Verdict]
    notes: dict[str, str] = Field(default_factory=dict, description="conversationId → 고칠 점")
    reviewer: str
    minutes: float = 0.0
