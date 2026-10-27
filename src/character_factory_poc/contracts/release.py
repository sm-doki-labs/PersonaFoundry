"""S11 릴리즈 패키지와 대상별 내보내기 계약 (LLD §5.17·§8.11, D-0044).

character-package-v1은 형식 중립 패키지의 매니페스트다(release-manifest-v1을 대체).
export-result-v1은 패키지 → 대상 시스템 적재물의 기록이다
(우리 앱: api-svc 시드 묶음, chat-svc 콘텐츠 트리).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import ArtifactRef, Strict


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
    shortPrompt: str


class Sft(Strict):
    datasetRev: str | None = None
    datasetDigest: str | None = None
    trainingRuns: list[str] = Field(default_factory=list, description="training-run-v2 경로")
    evalReport: str | None = None
    adoptedBinding: str | None = Field(default=None, description="G8에서 채택한 model_binding ref")


class GateRef(Strict):
    gate: str
    rev: str
    decision: str
    recordRef: str


@register("character-package-v1")
class CharacterPackage(Strict):
    schemaVersion: Literal["character-package-v1"] = "character-package-v1"
    characterId: str
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
