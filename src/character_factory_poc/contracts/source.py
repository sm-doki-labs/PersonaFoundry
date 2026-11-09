"""모티브 갈래 출처 계약 (D-0116, D-0120, D-0128, 계획 §4).

- source-pack-v1: 사람이 넣는 출처 묶음 목록. 원문 파일은 Git 밖에 두고 경로만 적는다.
- source-index-v1: s0가 원문을 읽어 정리한 통계와 사용 근거 점검 결과.
- source-digest-v1: 출처 정리 에이전트의 출력(화자 확인, 개인정보 표시, 대표 메시지, 관찰 요약).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

SubjectKind = Literal["PUBLIC_FIGURE", "PRIVATE_PERSON"]
TextKind = Literal["KAKAO_EXPORT", "INTERVIEW", "ARTICLE", "TRANSCRIPT"]
Register = Literal["FORMAL", "CASUAL"]


def default_register(kind: TextKind) -> Register:
    return "FORMAL" if kind in {"INTERVIEW", "ARTICLE"} else "CASUAL"


Speaker = Literal["SUBJECT", "USER", "OTHER"]
DigestCategory = Literal["DAILY", "AFFECTION", "CONFLICT", "ADVICE", "HUMOR", "WORK", "OTHER"]


class SourceSubject(Strict):
    displayName: str = Field(
        min_length=1, description="대상 인물 표시 이름(이 캐릭터 폴더 안에서만 쓴다)"
    )
    kind: SubjectKind


class UsageBasis(Strict):
    scope: str = Field(default="팀 내부 사용", description="사용 범위. 예: SW마에스트로 최종 발표")
    consentBy: str | None = Field(default=None, description="사인은 동의한 사람")
    consentDate: str | None = Field(default=None, description="사인은 동의한 날짜(YYYY-MM-DD)")
    notes: str = ""


class SourcePhoto(Strict):
    path: str = Field(min_length=1)
    origin: str = Field(default="", description="누가 찍었는지·어디서 받았는지")
    takenAt: str | None = None


class SourceText(Strict):
    textId: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    kind: TextKind
    path: str = Field(min_length=1)
    register: Register | None = None
    sourceUrl: str | None = None
    language: str = "ko"
    subjectSpeaker: str | None = Field(
        default=None, description="원문에서 대상 인물의 화자 이름(카톡 표시 이름, 인터뷰 화자)"
    )
    userSpeaker: str | None = Field(default=None, description="카톡에서 사용자(대화 상대)의 이름")
    date: str | None = Field(default=None, description="인터뷰·기사 날짜(YYYY-MM-DD)")


class HoldoutPolicy(Strict):
    fraction: float = Field(default=0.2, gt=0, lt=1, description="날짜 뒤쪽에서 떼어 둘 대화 비율")
    gapHours: float = Field(default=6.0, gt=0, description="이 시간보다 길게 끊기면 새 대화로 본다")


@register("source-pack-v1")
class SourcePack(Strict):
    schemaVersion: Literal["source-pack-v1"] = "source-pack-v1"
    subject: SourceSubject
    factsPath: str | None = Field(default=None, min_length=1, description="공개 사실 JSON 경로")
    knownFacts: dict[str, str] = Field(default_factory=dict)
    chapterTemplate: Literal["FAN_CALL", "FAMILY_CALL"] = Field(
        default_factory=lambda data: (
            "FAN_CALL" if data["subject"].kind == "PUBLIC_FIGURE" else "FAMILY_CALL"
        )
    )
    voiceId: UUID | None = Field(default=None, description="한국어 voice-svc 음성 UUID")
    usageBasis: UsageBasis = Field(default_factory=UsageBasis)
    photos: list[SourcePhoto] = Field(default_factory=list)
    texts: list[SourceText] = Field(min_length=1)
    holdout: HoldoutPolicy = Field(default_factory=HoldoutPolicy)


class TextStats(Strict):
    textId: str
    kind: TextKind
    register: Register | None = None
    sha256: str
    messages: int
    subjectMessages: int
    conversations: int
    first: str | None = None
    last: str | None = None


@register("source-index-v1")
class SourceIndex(Strict):
    schemaVersion: Literal["source-index-v1"] = "source-index-v1"
    characterId: str
    sourceRev: str
    subjectKind: SubjectKind
    texts: list[TextStats]
    photos: list[dict[str, str]] = Field(default_factory=list, description="경로·sha256")
    corpusMessages: int
    corpusSubjectMessages: int
    holdoutConversations: int
    holdoutMessages: int
    masked: dict[str, int] = Field(default_factory=dict, description="가린 항목 종류별 개수")
    otherParticipants: int = 0
    usageProblems: list[str] = Field(default_factory=list, description="이전 판의 사용 근거 안내")


class PiiFlag(Strict):
    msgId: str
    reason: str = Field(min_length=1)


class Representative(Strict):
    msgId: str
    category: DigestCategory
    why: str = Field(min_length=1)


class SpeakerCheck(Strict):
    confirmed: bool
    note: str = ""


@register("source-digest-v1")
class SourceDigest(Strict):
    schemaVersion: Literal["source-digest-v1"] = "source-digest-v1"
    speakerCheck: SpeakerCheck
    piiFlags: list[PiiFlag] = Field(default_factory=list)
    representative: list[Representative] = Field(default_factory=list)
    observations: list[str] = Field(
        default_factory=list, description="말투·관심사 관찰. 원문을 길게 옮기지 않는다"
    )
    qualityNotes: list[str] = Field(default_factory=list)
