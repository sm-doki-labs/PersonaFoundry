"""chapter-start-v1: 챕터별 시작 설정(D-0089, 마스터 지시서 MD-5.5~5.8).

서비스(chat-svc)는 고정 시작 대사 없이 장면 사실·장면 경계·챕터 관계 설정으로
첫 턴을 생성한다.
공장은 이 시작 설정 묶음을 인물마다 저작한다.
칸 이름은 chat-svc chapter-relationship-profile-v3와 맞춘다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict


class MoodRange(Strict):
    down: str = Field(min_length=1)
    start: str = Field(min_length=1)
    middle: str = Field(min_length=1)
    top: str = Field(min_length=1)


class RelationshipStart(Strict):
    speechLevel: Literal["POLITE", "CASUAL"]
    addresseeStance: str = Field(min_length=1, description="등급·호칭·허용 예외·전환 조건")
    entryPosture: list[str] = Field(min_length=1, max_length=2)
    presenceReason: str = Field(min_length=1)
    initiativePolicy: str = Field(min_length=1)
    expressionDelta: list[str] = Field(min_length=1, max_length=2)
    sceneWant: str = Field(min_length=1)
    moodRange: MoodRange
    trustedStory: str | None = None


class ChapterStart(Strict):
    chapterId: Literal["ch1", "ch2", "ch3"]
    sceneFacts: list[str] = Field(min_length=2, max_length=4)
    sceneBoundaries: list[str] = Field(min_length=1, max_length=3)
    relationship: RelationshipStart


@register("chapter-start-v1")
class ChapterStartSet(Strict):
    schemaVersion: Literal["chapter-start-v1"] = "chapter-start-v1"
    characterId: str
    planRev: str
    chapters: list[ChapterStart] = Field(min_length=3, max_length=3)

    @field_validator("chapters")
    @classmethod
    def _three(cls, v: list[ChapterStart]) -> list[ChapterStart]:
        if sorted(c.chapterId for c in v) != ["ch1", "ch2", "ch3"]:
            raise ValueError("chapters는 ch1, ch2, ch3 각각 하나씩이어야 한다")
        return sorted(v, key=lambda c: c.chapterId)
