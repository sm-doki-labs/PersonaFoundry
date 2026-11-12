"""모티브 갈래 출처 계약 (D-0116, D-0120, D-0128, 계획 §4).

- source-pack-v1: 사람이 넣는 출처 묶음 목록. 원문 파일은 Git 밖에 두고 경로만 적는다.
- source-index-v1: s0가 원문을 읽어 정리한 통계와 사용 근거 점검 결과.
- source-digest-v1: 출처 정리 에이전트의 출력(화자 확인, 개인정보 표시, 대표 메시지, 관찰 요약).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field, model_serializer

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

SubjectKind = Literal["PUBLIC_FIGURE", "PRIVATE_PERSON"]
ChapterTemplate = Literal["FAN_CALL", "FAMILY_CALL", "FRIEND_CHAT", "INTERVIEW"]
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


FACT_SHEET_MAX_LINES = 40
FACT_SHEET_MAX_CHARS = 300
_DATE = re.compile(r"^\d{4}-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])$")


def fact_sheet_lines(value) -> list[str]:
    """사용자가 준 사실표를 한 줄 한 사실로 정리한다. 앞뒤 공백을 떼고 빈 줄은 버린다.

    S8 [FACTS]에 글자 그대로 들어가므로 연락처와 프롬프트 구역·대화 예시처럼 보이는 줄은
    받지 않는다.
    """
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.splitlines()
    elif isinstance(value, list) and all(isinstance(x, str) for x in value):
        raw = [part for x in value for part in (x.splitlines() or [""])]
    else:
        raise ValueError("사실은 한 줄에 하나씩 글로 적어 주세요.")
    lines = [x.strip() for x in raw if x.strip()]
    if len(lines) > FACT_SHEET_MAX_LINES:
        raise ValueError(f"사실은 {FACT_SHEET_MAX_LINES}줄까지 적을 수 있어요.")
    # Lazy imports: parse imports this module, and the compiler is a standalone file.
    from character_factory_poc.stages.s0_source.parse import _ACCOUNT, _EMAIL, _PHONE
    from character_factory_poc.stages.s8_prompts.evidence_compiler import _text

    for n, line in enumerate(lines, 1):
        if len(line) > FACT_SHEET_MAX_CHARS:
            raise ValueError(f"사실 {n}번째 줄은 {FACT_SHEET_MAX_CHARS}자까지 적을 수 있어요.")
        if any(unicodedata.category(ch) == "Cc" for ch in line):
            raise ValueError(f"사실 {n}번째 줄에 보이지 않는 제어 문자가 있어요.")
        if (
            _EMAIL.search(line)
            or _PHONE.search(line)
            or any(not _DATE.match(m.group()) for m in _ACCOUNT.finditer(line))
        ):
            raise ValueError(
                f"사실 {n}번째 줄에 연락처나 계좌처럼 보이는 번호가 있어요. 빼고 적어 주세요."
            )
        try:
            _text(line, "factSheet", literal=True)
        except ValueError:
            raise ValueError(
                f"사실 {n}번째 줄은 대화 예시(질문:·답변:), 화살표(→, =>), "
                "[FACTS] 같은 구역 이름 없이 적어 주세요."
            ) from None
    return lines


FactSheet = Annotated[list[str], BeforeValidator(fact_sheet_lines)]


@register("source-pack-v1")
class SourcePack(Strict):
    schemaVersion: Literal["source-pack-v1"] = "source-pack-v1"
    subject: SourceSubject
    factsPath: str | None = Field(default=None, min_length=1, description="공개 사실 JSON 경로")
    knownFacts: dict[str, str] = Field(default_factory=dict)
    factSheet: FactSheet = Field(
        default_factory=list,
        description="사용자가 준 사실. 한 줄에 하나, S8 [FACTS]에 글자 그대로 넣는다",
    )
    chapterTemplate: ChapterTemplate = Field(
        default_factory=lambda data: (
            "FAN_CALL" if data["subject"].kind == "PUBLIC_FIGURE" else "FAMILY_CALL"
        )
    )
    voiceId: UUID | None = Field(default=None, description="한국어 voice-svc 음성 UUID")
    usageBasis: UsageBasis = Field(default_factory=UsageBasis)
    photos: list[SourcePhoto] = Field(default_factory=list)
    texts: list[SourceText] = Field(min_length=1)
    holdout: HoldoutPolicy = Field(default_factory=HoldoutPolicy)

    @model_serializer(mode="wrap")
    def _omit_empty_fact_sheet(self, handler):
        # Packs without a fact sheet keep their earlier bytes and hashes.
        data = handler(self)
        if not data.get("factSheet"):
            data.pop("factSheet", None)
        return data


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
