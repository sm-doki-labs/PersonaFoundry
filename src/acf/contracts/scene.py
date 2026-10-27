"""배경·장면 사실·자세 계약 (LLD §5.10a, D-0033~D-0035).

S4a 배경 후보 → G4a 선택(또는 직접 정의) → S4b 장면 사실 작성·자세 후보
→ G4b 선택(직접 정의·세부 수정) → S4 완성 이미지. 장면 사실 칸은 chat-svc 챕터 콘텐츠
(sceneFacts, meetingContexts, relationshipCanon, sceneBoundaries)와 이름을 맞춘다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from acf.common.schema import register
from acf.contracts.common import Strict
from acf.contracts.hero import ImageRef
from acf.contracts.planning import ChapterId
from acf.contracts.qa import QaSummary

CHAPTERS = ("ch1", "ch2", "ch3")


def _three(v: list) -> list:
    if sorted(c.chapterId for c in v) != list(CHAPTERS):
        raise ValueError("ch1, ch2, ch3 각각 하나씩이어야 한다")
    return sorted(v, key=lambda c: c.chapterId)


class BackgroundCandidate(Strict):
    candidateId: str = Field(pattern=r"^ch[123]-(b|u)\d+$")
    place: str = Field(min_length=1, description="장소 이름(실존 상호·작품을 특정하지 않는다)")
    timeOfDay: str = Field(min_length=1)
    why: str = Field(min_length=1, description="이 캐릭터가 여기 있는 이유(취향·생활과 연결)")
    props: list[str] = Field(default_factory=list, max_length=6)
    mood: str = Field(min_length=1, description="빛과 색")
    sceneFactsDraft: list[str] = Field(min_length=2, max_length=4)
    boundariesDraft: list[str] = Field(default_factory=list, max_length=4)
    plateBrief: str = Field(min_length=1, description="인물 없는 배경 사진 묘사(영어)")


class ChapterBackgrounds(Strict):
    chapterId: ChapterId
    candidates: list[BackgroundCandidate] = Field(min_length=1)


@register("background-candidates-output-v1")
class BackgroundOutput(Strict):
    """Location Scout 에이전트 출력."""

    schemaVersion: Literal["background-candidates-output-v1"] = "background-candidates-output-v1"
    chapters: list[ChapterBackgrounds] = Field(min_length=3, max_length=3)

    _v = field_validator("chapters")(classmethod(lambda cls, v: _three(v)))


class PlatedCandidate(BackgroundCandidate):
    plate: ImageRef | None = None
    qa: QaSummary | None = None  # 배경 사진 자동 검사 요약(D-0036)


class ChapterBackgroundSet(Strict):
    chapterId: ChapterId
    title: str
    arc: str
    candidates: list[PlatedCandidate] = Field(min_length=1)


@register("background-candidates-v1")
class BackgroundSet(Strict):
    """S4a rev(bg<k>) 하나의 후보 묶음과 배경 사진."""

    schemaVersion: Literal["background-candidates-v1"] = "background-candidates-v1"
    characterId: str
    backgroundRev: str = Field(pattern=r"^bg\d+$")
    planRev: str
    appearanceRev: str
    aspectRatio: str
    chapters: list[ChapterBackgroundSet] = Field(min_length=3, max_length=3)

    _v = field_validator("chapters")(classmethod(lambda cls, v: _three(v)))


@register("background-selection-v1")
class BackgroundSelection(Strict):
    """G4a 결정. 챕터마다 후보 하나를 고르거나(picks) 원하는 배경을 한두 줄로 정의한다(custom)."""

    schemaVersion: Literal["background-selection-v1"] = "background-selection-v1"
    backgroundRev: str
    picks: dict[str, str] = Field(default_factory=dict)
    custom: dict[str, str] = Field(default_factory=dict)


class SceneChapter(Strict):
    chapterId: ChapterId
    source: Literal["CANDIDATE", "USER"]
    candidateId: str | None = None
    place: str = Field(min_length=1)
    timeOfDay: str = Field(min_length=1)
    props: list[str] = Field(default_factory=list)
    mood: str = Field(min_length=1)
    sceneFacts: list[str] = Field(min_length=2, max_length=5)
    meetingContext: str = Field(min_length=1, description="두 사람이 이 자리에 온 경위")
    relationshipCanon: list[str] = Field(default_factory=list, max_length=4)
    sceneBoundaries: list[str] = Field(min_length=1, max_length=5)
    plateBrief: str = Field(min_length=1)


@register("scene-writer-output-v1")
class SceneWriterOutput(Strict):
    """Scene Writer 에이전트 출력: 고른 배경으로 챕터 사실을 이어서 쓴다."""

    schemaVersion: Literal["scene-writer-output-v1"] = "scene-writer-output-v1"
    chapters: list[SceneChapter] = Field(min_length=3, max_length=3)

    _v = field_validator("chapters")(classmethod(lambda cls, v: _three(v)))


class PlatedScene(SceneChapter):
    plate: ImageRef
    qa: QaSummary | None = None  # 배경 사진 자동 검사 요약(D-0036)


@register("scene-plan-v1")
class ScenePlan(Strict):
    """챕터 사실 3개(앱 챕터 콘텐츠의 사실 영역)와 확정 배경 사진."""

    schemaVersion: Literal["scene-plan-v1"] = "scene-plan-v1"
    characterId: str
    sceneRev: str = Field(pattern=r"^ps\d+$")
    backgroundRev: str
    planRev: str
    aspectRatio: str
    chapters: list[PlatedScene] = Field(min_length=3, max_length=3)

    _v = field_validator("chapters")(classmethod(lambda cls, v: _three(v)))


POSE_FIELDS = ("body", "hands", "props", "gaze", "expression", "shot", "outfit", "motionHint")


class PoseCandidate(Strict):
    poseId: str = Field(pattern=r"^ch[123]-p\d+$")
    title: str = Field(min_length=1)
    body: str = Field(min_length=1, description="몸 방향·앉음/서 있음")
    hands: str = Field(min_length=1, description="손 위치와 소품. 얼굴에 닿지 않는다(D-0027)")
    props: str = ""
    gaze: str = Field(min_length=1)
    expression: str = Field(min_length=1, description="관계 단계에 맞는 표정")
    shot: str = Field(min_length=1, description="9:16 세로 구도와 샷 크기")
    outfit: str = Field(min_length=1, description="이 챕터의 의상")
    motionHint: str = Field(min_length=1, description="영상 첫 장면에서 이어질 움직임")
    animatable: bool = True


class ChapterPoses(Strict):
    chapterId: ChapterId
    candidates: list[PoseCandidate] = Field(min_length=1)


@register("pose-candidates-output-v1")
class PoseOutput(Strict):
    schemaVersion: Literal["pose-candidates-output-v1"] = "pose-candidates-output-v1"
    chapters: list[ChapterPoses] = Field(min_length=3, max_length=3)

    _v = field_validator("chapters")(classmethod(lambda cls, v: _three(v)))


@register("pose-candidates-v1")
class PoseSet(Strict):
    schemaVersion: Literal["pose-candidates-v1"] = "pose-candidates-v1"
    characterId: str
    sceneRev: str
    chapters: list[ChapterPoses] = Field(min_length=3, max_length=3)

    _v = field_validator("chapters")(classmethod(lambda cls, v: _three(v)))


@register("pose-selection-v1")
class PoseSelection(Strict):
    """G4b 결정. 고르기(picks), 직접 정의(custom), 고른 자세의 세부 수정(tweaks)."""

    schemaVersion: Literal["pose-selection-v1"] = "pose-selection-v1"
    sceneRev: str
    picks: dict[str, str] = Field(default_factory=dict)
    custom: dict[str, str] = Field(default_factory=dict)
    tweaks: dict[str, dict[str, str]] = Field(default_factory=dict)


class ResolvedPose(Strict):
    chapterId: ChapterId
    source: Literal["CANDIDATE", "USER"]
    poseId: str | None = None
    title: str = ""
    body: str = ""
    hands: str = ""
    props: str = ""
    gaze: str = ""
    expression: str = ""
    shot: str = ""
    outfit: str = ""
    motionHint: str = ""
    customText: str = ""
    tweaked: list[str] = Field(default_factory=list)


@register("pose-plan-v1")
class PosePlan(Strict):
    schemaVersion: Literal["pose-plan-v1"] = "pose-plan-v1"
    characterId: str
    sceneRev: str
    chapters: list[ResolvedPose] = Field(min_length=3, max_length=3)

    _v = field_validator("chapters")(classmethod(lambda cls, v: _three(v)))


@register("frames-inputs-v2")
class FramesInputsV2(Strict):
    """S4 완성 이미지 입력 고정본: 기준 얼굴, 장면 사실·배경 사진, 자세."""

    schemaVersion: Literal["frames-inputs-v2"] = "frames-inputs-v2"
    appearanceRev: str
    planRev: str
    sceneRev: str
    aspectRatio: str
    referenceImage: ImageRef
    identityReference: ImageRef
    referenceCrop: Literal["face", "full"]
    cropNote: str = ""
    regenerate: list[ChapterId] = Field(default_factory=lambda: list(CHAPTERS))
    carriedFrom: str | None = None
    revisionNotes: dict[str, str] = Field(default_factory=dict)
