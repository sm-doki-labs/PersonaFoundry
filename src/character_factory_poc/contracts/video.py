"""S5·S6 영상 계약 (LLD §5.11, D-0028, D-0030, D-0031, D-0038, D-0040, D-0041)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.hero import ImageRef

# S5 소개 영상은 ...-intro-vi<k>-<n>, S6 동작 영상은 ...-ch<N>-<actionKey>-va<k>-<n>(D-0038)
VIDEO_ID = r"^vd-cf-\d{8}-[a-z0-9-]+-(intro-vi|ch[123]-[a-z0-9_]+-va)\d+-\d+$"
ACTION_KEY = r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"  # 앱 clip_key(예: glad_good, sad_good_strong)
ACTION_ID = r"^ch[123]-[a-z][a-z0-9]*(_[a-z0-9]+)*$"
# 앱 통화 영상 분류(api-svc character_clip, clip_taxonomy). 말하기·후속 영상은 만들지 않는다(D-0040)
PlayType = Literal["idle", "reaction"]
PickRole = Literal["emotion", "special"]
ActionCategory = Literal["aegyo", "touch"]  # 앱의 sexy(allure)·private는 공장 기본에서 뺀다
Mood = Literal["good", "bad"]


class VideoSettings(Strict):
    prompt: str = Field(min_length=1)
    duration: int = Field(ge=1, le=15)
    resolution: Literal["480p", "720p", "1080p"]
    aspectRatio: str | None = None
    generateAudio: bool = False


class FirstFrameSource(Strict):
    """첫 프레임을 어떻게 만들었는지. hero는 G2 대표 이미지 그대로, generated는 대표 이미지를
    참조로 목표 비율의 사진을 새로 만들어 자른 것이다(D-0031)."""

    mode: Literal["hero", "generated"]
    hero: ImageRef
    prompt: str = ""
    negativePrompt: str = ""
    provider: str = ""
    model: str = ""
    rawSize: list[int] | None = None
    croppedSize: list[int] | None = None


@register("intro-inputs-v2")
class IntroInputs(Strict):
    """S5 실행 입력 고정본. 첫 프레임과 그 출처(D-0031)를 함께 고정한다.

    v1(대표 이미지 그대로)은 실제 산출물 없이 v2로 바뀌었다."""

    schemaVersion: Literal["intro-inputs-v2"] = "intro-inputs-v2"
    appearanceRev: str = Field(pattern=r"^ar\d+$")
    planRev: str | None = None
    firstFrame: ImageRef
    firstFrameSource: FirstFrameSource
    provider: str
    model: str
    settings: VideoSettings
    candidates: int = Field(ge=1, le=8)


@register("video-job-v1")
class VideoJob(Strict):
    """원격(또는 웹) 작업 하나. 제출 직후 jobId를 먼저 남겨 끊겨도 같은 작업을 다시 받는다."""

    schemaVersion: Literal["video-job-v1"] = "video-job-v1"
    videoId: str = Field(pattern=VIDEO_ID)
    candidateId: str = Field(pattern=r"^v\d+$")
    stage: Literal["s5", "s6"]
    provider: str
    model: str
    jobId: str
    status: Literal["SUBMITTED", "DONE", "FAILED"]
    settings: VideoSettings
    firstFrameSha256: str
    estCostUsd: float | None = None
    error: str = ""


class Probe(Strict):
    tool: str | None
    durationS: float | None = None
    width: int | None = None
    height: int | None = None
    note: str = ""


@register("video-asset-v1")
class VideoAsset(Strict):
    schemaVersion: Literal["video-asset-v1"] = "video-asset-v1"
    videoId: str = Field(pattern=VIDEO_ID)
    candidateId: str = Field(pattern=r"^v\d+$")
    jobId: str
    provider: str
    model: str
    filePath: str
    fileSha256: str
    bytes: int = Field(gt=0)
    settings: VideoSettings
    probe: Probe
    estCostUsd: float | None = None


@register("intro-video-approved-v1")
class ApprovedIntro(Strict):
    """G5에서 사람이 고른 소개 영상."""

    schemaVersion: Literal["intro-video-approved-v1"] = "intro-video-approved-v1"
    characterId: str
    introRev: str = Field(pattern=r"^vi\d+$")
    appearanceRev: str
    videoId: str = Field(pattern=VIDEO_ID)
    video: ImageRef
    notes: str = ""


# ------------------------------------------------ S6 동작 영상 (D-0038, D-0040, D-0041)
# v1(동작 카탈로그 8개, D-0039)은 실제 산출물 없이 v2(앱 통화 영상 이름, D-0040)로 바뀌었다.


class ActionSpec(Strict):
    """챕터 한 장면에서 만들 영상 하나.

    actionId = <chapterId>-<actionKey>이고 actionKey는 앱 clip_key다."""

    actionId: str = Field(pattern=ACTION_ID)
    actionKey: str = Field(pattern=ACTION_KEY)
    playType: PlayType
    pickRole: PickRole | None = None  # 대기는 None, 감정 반응은 emotion, 특별 행동은 special
    actionCategory: ActionCategory | None = None  # 특별 행동만. sexy는 공장에서 만들지 않는다
    mood: Mood  # 시작·끝 표정. good이면 미소 첫 프레임, bad면 무표정 첫 프레임에서 시작한다
    title: str = ""
    description: str = ""
    useWhen: str = ""
    duration: int = Field(ge=1, le=15)
    prompt: str = Field(min_length=1)
    reviewNote: str = ""  # G5b 수정 요청으로 다시 만들 때 붙인 사람 메모

    @model_validator(mode="after")
    def _roles(self) -> ActionSpec:
        if (self.playType == "idle") != (self.pickRole is None):
            raise ValueError("대기(idle)만 pickRole이 없고, 반응은 emotion 또는 special이다")
        if (self.pickRole == "special") != (self.actionCategory is not None):
            raise ValueError("특별 행동만 actionCategory(aegyo·touch)를 가진다")
        return self


class FrameEdit(Strict):
    """무표정 첫 프레임을 어떻게 만들었는지(D-0041). G4 이미지를 참조로 표정만 바꾼다."""

    source: ImageRef  # G4 승인 이미지(미소 첫 프레임)
    prompt: str
    negativePrompt: str = ""
    provider: str
    model: str
    rawSize: list[int]
    croppedSize: list[int]
    reusedFrom: str | None = None  # 부분 재생성 때 가져온 rev


class ActionChapter(Strict):
    chapterId: Literal["ch1", "ch2", "ch3"]
    frameId: str = Field(pattern=r"^ch[123]-f\d+$")
    stageNote: str = ""  # 관계 단계 메모(프롬프트에 붙인 문장)
    goodFrame: ImageRef  # G4 승인 이미지 복사본. 미소 출발 영상의 첫 프레임
    badFrame: ImageRef | None = None  # 무표정 출발 영상이 있을 때만
    badFrameSource: FrameEdit | None = None
    actions: list[ActionSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _bad_frame(self) -> ActionChapter:
        needs = any(a.mood == "bad" for a in self.actions)
        if needs != (self.badFrame is not None) or (self.badFrame is None) != (
            self.badFrameSource is None
        ):
            raise ValueError("무표정 출발 영상이 있을 때만 badFrame과 badFrameSource를 둔다")
        return self


@register("action-inputs-v2")
class ActionInputs(Strict):
    """S6 실행 입력 고정본. G4 승인 이미지(챕터마다 1장)와 동작 목록·설정을 고정한다."""

    schemaVersion: Literal["action-inputs-v2"] = "action-inputs-v2"
    frameRev: str = Field(pattern=r"^fr\d+$")
    appearanceRev: str
    planRev: str
    provider: str
    model: str
    preset: str = ""  # l2 | standard | custom
    resolution: Literal["480p", "720p", "1080p"]
    aspectRatio: str | None = None
    generateAudio: bool = False
    candidates: int = Field(ge=1, le=4)
    previousRev: str | None = None  # G5b 수정 요청 뒤 새 rev면 직전 rev
    regenerate: list[str] = Field(default_factory=list)  # 다시 만든 actionId. 나머지는 재사용
    chapters: list[ActionChapter] = Field(min_length=3, max_length=3)


@register("action-clip-v2")
class ActionClip(Strict):
    """동작 영상 후보 하나. 재사용한 영상은 reusedFrom에 원래 rev가 남고 videoId는 그대로다."""

    schemaVersion: Literal["action-clip-v2"] = "action-clip-v2"
    actionId: str = Field(pattern=ACTION_ID)
    chapterId: Literal["ch1", "ch2", "ch3"]
    actionKey: str = Field(pattern=ACTION_KEY)
    playType: PlayType
    pickRole: PickRole | None = None
    actionCategory: ActionCategory | None = None
    mood: Mood
    title: str = ""
    frameId: str
    asset: VideoAsset
    reusedFrom: str | None = None


class ApprovedClip(Strict):
    """앱 내보내기가 그대로 쓰는 칸. stage = 챕터 번호(ch1 → 1)이고 clipKey = 앱 clip_key다."""

    actionId: str = Field(pattern=ACTION_ID)
    chapterId: Literal["ch1", "ch2", "ch3"]
    stage: int = Field(ge=1, le=3)
    clipKey: str = Field(pattern=ACTION_KEY)
    playType: PlayType
    pickRole: PickRole | None = None
    actionCategory: ActionCategory | None = None
    mood: Mood
    title: str = ""
    description: str = ""
    useWhen: str = ""
    duration: int = Field(ge=1, le=15)
    videoId: str = Field(pattern=VIDEO_ID)
    video: ImageRef

    @model_validator(mode="after")
    def _stage(self) -> ApprovedClip:
        if self.stage != int(self.chapterId[2]):
            raise ValueError("stage는 챕터 번호와 같다")
        return self


@register("action-videos-approved-v2")
class ApprovedActions(Strict):
    """G5b에서 사람이 고른 동작 영상. 앱 통화 영상 세트(R1 내보내기)의 입력이다."""

    schemaVersion: Literal["action-videos-approved-v2"] = "action-videos-approved-v2"
    characterId: str
    actionRev: str = Field(pattern=r"^va\d+$")
    frameRev: str = Field(pattern=r"^fr\d+$")
    appearanceRev: str
    planRev: str
    clips: list[ApprovedClip] = Field(min_length=3)
    excluded: list[str] = Field(default_factory=list)  # 고르지 않고 뺀 actionId
    notes: str = ""

    @field_validator("clips")
    @classmethod
    def _every_chapter(cls, v: list[ApprovedClip]) -> list[ApprovedClip]:
        if sorted({c.chapterId for c in v}) != ["ch1", "ch2", "ch3"]:
            raise ValueError("clips는 ch1, ch2, ch3 각각 하나 이상이어야 한다")
        ids = [c.actionId for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("한 동작에서 영상은 하나만 고른다")
        return v
