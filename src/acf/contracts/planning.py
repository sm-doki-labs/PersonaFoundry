"""기획 씨앗·변형·선택 계약 (LLD §5.9a, D-0033~D-0035).

사람은 씨앗(대표 성격·직업·나이·성별·간단한 배경)만 쓰고, 에이전트가 상세 변형을 만든다.
G3에서 사람이 한 안을 고르거나(고친 칸 포함) 직접 쓴 안을 정리한 u1을 고르면
character-plan-v2가 고정된다.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from acf.common.schema import register
from acf.contracts.common import Strict

Gender = Literal["female", "male", "other"]
EvidenceKindV2 = Literal["SEED", "USER", "AGENT", "PRESET", "REFERENCE", "APPEARANCE"]
RelationStage = Literal["STRANGER", "ACQUAINTANCE", "FLIRTING", "DATING"]
Slot = Literal["GET_TO_KNOW", "FLIRT", "CONFESS"]
ChapterId = Literal["ch1", "ch2", "ch3"]

# 앱의 게이트 챕터 3개(친해지기 → 썸타기 → 고백하기)와 관계 단계.
# 영상통화 챕터는 세 장소를 다시 쓴다.
CHAPTER_SLOTS: dict[str, dict[str, str]] = {
    "ch1": {
        "slot": "GET_TO_KNOW",
        "title": "친해지기",
        "entry": "STRANGER",
        "target": "ACQUAINTANCE",
    },
    "ch2": {"slot": "FLIRT", "title": "썸타기", "entry": "ACQUAINTANCE", "target": "FLIRTING"},
    "ch3": {"slot": "CONFESS", "title": "고백하기", "entry": "FLIRTING", "target": "DATING"},
}
# 성격 칸. 근거에 외모(APPEARANCE)를 쓸 수 없다(D-0005).
PERSONALITY_FIELDS_V2 = (
    "coreTraits",
    "contrastTrait",
    "choices",
    "wantsAndFears",
    "misreadings",
    "voiceSummary",
)
# G3에서 사람이 고칠 수 있는 칸.
EDITABLE_FIELDS = (
    "name",
    "age",
    "gender",
    "job",
    "tagline",
    "background",
    "coreTraits",
    "contrastTrait",
    "choices",
    "lifeAndTastes",
    "wantsAndFears",
    "misreadings",
    "voiceSummary",
    "voiceExamples",
    "boundaries",
    "profileCard",
    "notes",
)


@register("plan-seed-v1")
class PlanSeed(Strict):
    """사람이 G2 직후 쓰는 기획 씨앗. 비운 칸은 에이전트가 채운다."""

    schemaVersion: Literal["plan-seed-v1"] = "plan-seed-v1"
    characterId: str
    seedRev: str = Field(pattern=r"^sd\d+$")
    personality: str = Field(min_length=1, description="대표 성격 한두 구절")
    job: str = ""
    age: int | None = Field(default=None, ge=18)
    gender: Gender | None = None
    background: str = ""
    notes: str = ""


class EvidenceV2(Strict):
    kind: EvidenceKindV2
    ref: str = ""
    quote: str = ""


class Choice(Strict):
    """같은 상황에서의 첫 행동. 변형끼리는 상황을 같게 두고 행동이 달라야 한다."""

    situation: str = Field(min_length=1)
    firstMove: str = Field(min_length=1)


class TmiItem(Strict):
    text: str = Field(min_length=1)
    revealStage: int = Field(ge=0, le=3)


class ProfileCard(Strict):
    """앱 프로필 카드(api-svc character_profile_card) 칸."""

    hobby: str = ""
    likes: str = ""
    dislikes: str = ""
    favoriteFoods: str = ""
    favoriteDrink: str = ""
    idealDate: str = ""
    everydayHabit: str = ""
    mbti: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=4)
    tmi: list[TmiItem] = Field(default_factory=list)

    @field_validator("mbti")
    @classmethod
    def _mbti(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"[EI][NS][TF][JP]", v):
            raise ValueError("mbti는 ENFP 같은 네 글자다")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        for t in v:
            if not 1 <= len(t) <= 12 or t.startswith("#"):
                raise ValueError("태그는 # 없이 1~12자다")
        return v


class ArcChapter(Strict):
    """챕터의 관계 흐름. 장소는 정하지 않는다(배경은 S4a에서 고른다)."""

    chapterId: ChapterId
    slot: Slot
    title: str = Field(min_length=1)
    entryStage: RelationStage
    targetStage: RelationStage
    arc: str = Field(min_length=1, description="이 챕터에서 관계가 어떻게 움직이는지 한 줄")


@register("character-plan-v2")
class CharacterPlanV2(Strict):
    schemaVersion: Literal["character-plan-v2"] = "character-plan-v2"
    characterId: str
    planRev: str = Field(pattern=r"^pr\d+$")
    variantId: str = Field(pattern=r"^(v|u)\d+$")
    seedRev: str = Field(pattern=r"^sd\d+$")
    name: str = Field(min_length=1)
    age: int = Field(ge=18)
    gender: Gender
    job: str = Field(min_length=1)
    tagline: str = Field(min_length=1, max_length=200)
    background: str = Field(min_length=1)
    coreTraits: list[str] = Field(min_length=1, max_length=4)
    contrastTrait: str = Field(min_length=1)
    choices: list[Choice] = Field(min_length=3, max_length=5)
    lifeAndTastes: list[str] = Field(min_length=3, max_length=8)
    wantsAndFears: list[str] = Field(min_length=1, max_length=4)
    misreadings: list[str] = Field(min_length=1, max_length=3)
    voiceSummary: str = Field(min_length=1)
    voiceExamples: list[str] = Field(min_length=2, max_length=3)
    boundaries: list[str] = Field(min_length=1, max_length=4)
    profileCard: ProfileCard = Field(default_factory=ProfileCard)
    chapterArc: list[ArcChapter] = Field(min_length=3, max_length=3)
    evidence: dict[str, list[EvidenceV2]] = Field(default_factory=dict)
    appearanceRev: str | None = None
    notes: str = ""

    @field_validator("chapterArc")
    @classmethod
    def _arc_slots(cls, v: list[ArcChapter]) -> list[ArcChapter]:
        if sorted(c.chapterId for c in v) != ["ch1", "ch2", "ch3"]:
            raise ValueError("chapterArc는 ch1, ch2, ch3 각각 하나씩이어야 한다")
        for c in v:
            want = CHAPTER_SLOTS[c.chapterId]
            got = (c.slot, c.entryStage, c.targetStage)
            if got != (want["slot"], want["entry"], want["target"]):
                raise ValueError(
                    f"{c.chapterId}는 {want['slot']} {want['entry']}→{want['target']}이어야 한다"
                )
        return sorted(v, key=lambda c: c.chapterId)

    @model_validator(mode="after")
    def _personality_not_from_appearance(self):
        for f in PERSONALITY_FIELDS_V2:
            for ev in self.evidence.get(f, []):
                if ev.kind == "APPEARANCE":
                    raise ValueError(f"{f}의 근거로 APPEARANCE를 쓸 수 없다(D-0005)")
        return self

    # S7·S8이 v1과 같은 이름으로 읽는다.
    @property
    def chapters(self) -> list[ArcChapter]:
        return self.chapterArc


@register("plan-variants-output-v1")
class PlanVariantsOutput(Strict):
    """Planner 에이전트 출력: 같은 씨앗의 상세 변형 N개."""

    schemaVersion: Literal["plan-variants-output-v1"] = "plan-variants-output-v1"
    variants: list[CharacterPlanV2] = Field(min_length=1, max_length=5)
    axisNote: str = Field(default="", description="변형끼리 무엇이 다른지 한 줄")


@register("plan-variants-v1")
class PlanVariants(Strict):
    """S3 rev 하나의 후보 묶음. G3 페이지가 이것을 보여 준다."""

    schemaVersion: Literal["plan-variants-v1"] = "plan-variants-v1"
    characterId: str
    planRev: str = Field(pattern=r"^pr\d+$")
    seedRev: str
    seedSha256: str
    mode: Literal["variants", "own"]
    axisNote: str = ""
    candidates: list[CharacterPlanV2] = Field(min_length=1)


@register("plan-selection-v1")
class PlanSelection(Strict):
    schemaVersion: Literal["plan-selection-v1"] = "plan-selection-v1"
    planRev: str
    selected: str
    editedFields: list[str] = Field(default_factory=list)
