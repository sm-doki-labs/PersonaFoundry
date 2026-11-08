"""S11 릴리즈 패키지와 대상별 내보내기 계약 (LLD §5.17·§8.11, D-0044).

character-package-v1은 형식 중립 패키지의 매니페스트다(release-manifest-v1을 대체).
export-result-v1은 패키지 → 대상 시스템 적재물의 기록이다
(우리 앱: api-svc 시드 묶음, chat-svc 콘텐츠 트리).
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import ArtifactRef, Strict
from character_factory_poc.contracts.source import SubjectKind


class PackageFile(Strict):
    path: str = Field(description="패키지 루트 기준 상대 경로")
    sha256: str
    bytes: int


class TmiItem(Strict):
    text: str
    revealStage: int = Field(ge=0, description="0이면 처음부터 공개")


class Profile(Strict):
    """앱 프로필 카드로 가는 칸. 출처는 G3 기획서(character-plan-v2)다."""

    name: str
    gender: Literal["female", "male", "other"]
    age: str
    job: str = ""
    tagline: str = ""
    description: str = ""
    hobby: str = ""
    likes: str = ""
    dislikes: str = ""
    mbti: str = ""
    tags: list[str] = Field(default_factory=list, max_length=4)
    tmiItems: list[TmiItem] = Field(default_factory=list)


class Appearance(Strict):
    appearanceRev: str
    heroImage: str = Field(description="PackageFile.path")
    spec: str


class Chapter(Strict):
    chapterNo: int = Field(ge=1)
    chapterId: str
    title: str
    relationshipStage: str
    intro: str = ""
    goal: str = ""
    facts: str = Field(description="챕터 사실 파일(PackageFile.path)")
    frame: str = Field(description="G4 승인 완성 이미지")
    background: str = ""


class Video(Strict):
    videoId: str
    kind: Literal["INTRO", "ACTION"]
    chapterNo: int | None = None
    clipKey: str = Field(default="", description="앱 통화 영상 clip_key(D-0040)")
    title: str = ""
    description: str = ""
    useWhen: str = ""
    expression: str = ""
    durationS: float
    file: str
    provider: str
    synthetic: bool = Field(description="가짜 공급자로 만든 영상이면 True(PoC)")


class Persona(Strict):
    personaVersion: str
    traitSheet: str
    longPrompt: str
    shortPrompt: str | None = None


class Sft(Strict):
    datasetRev: str | None = None
    datasetDigest: str | None = None
    trainingRuns: list[str] = Field(default_factory=list, description="training-run-v2 경로")
    evalReport: str | None = None
    adoptedBinding: str | None = Field(default=None, description="G8에서 채택한 model_binding ref")
    serving: str | None = Field(
        default=None,
        description="채택 어댑터 서빙 기록(sft-serving-v1, PackageFile.path). "
        "실제 gemma_qlora SFT를 채택했을 때만 있다",
    )


class AdapterFile(Strict):
    """패키지에 복사하지 않고 해시로만 참조하는 어댑터 파일."""

    path: str = Field(description="adapterRef 기준 파일 이름")
    sha256: str
    bytes: int


class ServingGeneration(Strict):
    """서빙 생성 설정. 이름은 serve_qlora 요청 본문과 같다(D-0077 선별 설정)."""

    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    max_new_tokens: int = 512


class CheckpointSelectionRef(Strict):
    path: str = Field(description="캐릭터 폴더 기준 checkpoint-selection.json 경로")
    sha256: str
    decision: str | None = None


@register("sft-serving-v1")
class SftServing(Strict):
    """G8 채택 어댑터를 그대로 서빙하기 위한 기록. 가중치는 해시로 참조한다."""

    schemaVersion: Literal["sft-serving-v1"] = "sft-serving-v1"
    characterId: str
    armId: Literal["SHORT_GEMMA_SFT"] = "SHORT_GEMMA_SFT"
    adoptedBinding: str
    provider: Literal["gemma_qlora"]
    trainingRun: ArtifactRef = Field(description="패키지 안 training-run-v2 경로와 해시")
    baseModel: str
    baseModelRevision: str = ""
    chatTemplate: str
    thinkingEnabled: Literal[False] = False
    checkpointId: str
    adapterRef: str = Field(description="어댑터 폴더의 로컬 경로")
    adapterFiles: list[AdapterFile] = Field(min_length=2)
    generation: ServingGeneration = Field(default_factory=ServingGeneration)
    runtimeVersions: dict[str, Any] = Field(default_factory=dict)
    checkpointSelection: CheckpointSelectionRef | None = None


class GateRef(Strict):
    gate: str
    rev: str
    decision: str
    recordRef: str


class TwinRelease(Strict):
    origin: Literal["SOURCE"] = "SOURCE"
    originLabel: Literal["트윈"] = "트윈"
    sourcePackSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    subjectKind: SubjectKind
    usageScope: str
    consentRecorded: bool
    modelMode: Literal["TRAIN", "BIND_EXISTING", "PROMPT_ONLY"]
    chapterTemplate: Literal["FAN_CALL", "FAMILY_CALL"]
    startButtonLabel: str
    voiceId: UUID | None = None
    # OpenAI 호환 서빙에서 요청 model로 쓰는 공개 별칭. 주소나 키를 받지 않는다.
    servingRoute: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    servingModel: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$"
    )
    apiKeyEnv: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    trainingRecord: ArtifactRef | None = Field(
        default=None, description="캐릭터 폴더 기준 원본 학습·연결 기록"
    )
    comparisonReport: str | None = Field(default=None, description="캐릭터 폴더 기준 외부 참조")
    disclosure: Literal["AI 생성 · 본인과 무관한 기술 시연"] = "AI 생성 · 본인과 무관한 기술 시연"


@register("character-package-v1")
class CharacterPackage(Strict):
    schemaVersion: Literal["character-package-v1"] = "character-package-v1"
    characterId: str
    twin: TwinRelease | None = Field(default=None, exclude_if=lambda v: v is None)
    packageRev: str = Field(pattern=r"^pk\d+$")
    locale: Literal["ko"] = "ko"
    builtAt: str
    profile: Profile
    appearance: Appearance
    chapters: list[Chapter] = Field(min_length=1)
    videos: list[Video]
    persona: Persona
    sft: Sft = Field(default_factory=Sft)
    gates: list[GateRef]
    files: list[PackageFile] = Field(
        description="패키지에 든 모든 파일. 적재 전에 해시를 다시 잰다"
    )


class ExportOutput(Strict):
    system: Literal["api-svc", "chat-svc"]
    kind: Literal["seed-bundle", "content-tree"]
    path: str
    sha256: str


class MappingRow(Strict):
    source: str = Field(description="패키지 칸, 예: profile.tagline")
    target: str = Field(description="대상 칸, 예: api-svc character.tagline")
    note: str = ""


class VerifyStep(Strict):
    name: str
    ok: bool
    detail: str = ""


class Verification(Strict):
    status: Literal["NOT_RUN", "PASSED", "FAILED"]
    disposableDb: bool = Field(
        description="일회용 DB에서만 적재한다. dev/stage에는 연결하지 않는다"
    )
    steps: list[VerifyStep] = Field(default_factory=list)


@register("export-result-v1")
class ExportResult(Strict):
    schemaVersion: Literal["export-result-v1"] = "export-result-v1"
    characterId: str
    package: ArtifactRef
    target: Literal["doki-app"]
    targetVersions: dict[str, str] = Field(description="저장소별 alembic head와 커밋")
    outputs: list[ExportOutput]
    mapping: list[MappingRow]
    unmapped: list[str] = Field(default_factory=list, description="대상에 칸이 없어 버린 패키지 칸")
    verification: Verification
