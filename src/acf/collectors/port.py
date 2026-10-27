"""화제성 순위 수집 포트 (P-14, P-21, Q-0013).

출처마다 다른 발표 형식을 흡수해 `popularity-ranking-v2`의 목록 하나로 바꾸는 공용 형식이다.
이용 조건 확인 기록을 출처와 함께 다니게 해서, 산출물마다 "무엇을 언제 확인했는지"가 남게 한다.
항목(인물 한 명)은 계약에 출처 칸이 없으므로, 목록의 `url`·`retrievedAt`과 수집 기록의
`listId`로 항목마다 근거를 되짚는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from acf.contracts.reference import RankingEntry

Gender = Literal["female", "male", "any"]


@dataclass(frozen=True)
class CategorySpec:
    """출처가 공개하는 분류 하나. `gender`는 그 분류가 담는 인물의 성별이다."""

    key: str
    slug: str
    label: str
    gender: Gender
    url: str


@dataclass(frozen=True)
class TermsCheck:
    """이용 조건 확인 기록. 확인 날짜·본문 요지·판단을 함께 남긴다.

    `robots_allows`·`terms_allows`가 `None`이면 "그 문서로는 판단하지 못했다"는 뜻이고,
    `human_review`에 사람이 다시 볼 항목을 적는다. 명시적으로 금지한 기록(`False`)만 실행을 막는다.
    """

    checked_on: str
    robots_url: str
    robots_rule: str
    robots_allows: bool | None
    terms_url: str
    terms_note: str
    terms_allows: bool | None
    human_review: bool = False
    notes: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        """명시적으로 금지한 기록이 있으면 실행하지 않는다(P-21)."""
        return self.robots_allows is not False and self.terms_allows is not False

    def as_record(self) -> dict[str, Any]:
        return {
            "checkedOn": self.checked_on,
            "robotsUrl": self.robots_url,
            "robotsRule": self.robots_rule,
            "robotsAllows": self.robots_allows,
            "termsUrl": self.terms_url,
            "termsNote": self.terms_note,
            "termsAllows": self.terms_allows,
            "humanReview": self.human_review,
            "notes": list(self.notes),
        }


@dataclass
class CollectedList:
    """한 번의 수집으로 얻은 목록 하나(계약의 `RankingList`에 대응)."""

    list_id: str
    source: str
    category: str
    period: str
    gender: Gender
    url: str
    retrieved_at: str
    entries: list[RankingEntry]
    note: str = ""

    def as_contract(self) -> dict[str, Any]:
        """계약에 넣을 사전. 점수가 없으면 `score` 칸을 넣지 않는다(null과 구분)."""
        entries: list[dict[str, Any]] = []
        for e in self.entries:
            item: dict[str, Any] = {"rank": e.rank, "name": e.name}
            if e.score is not None:
                item["score"] = e.score
            entries.append(item)
        return {
            "listId": self.list_id,
            "source": self.source,
            "category": self.category,
            "period": self.period,
            "retrievedAt": self.retrieved_at,
            "url": self.url,
            "entries": entries,
        }

    def as_record(self, terms: TermsCheck) -> dict[str, Any]:
        """항목마다 되짚을 수 있는 수집 기록. 출처 URL·수집 시각·이용 조건 확인 날짜를 담는다."""
        return {
            "listId": self.list_id,
            "url": self.url,
            "retrievedAt": self.retrieved_at,
            "period": self.period,
            "category": self.category,
            "gender": self.gender,
            "entryCount": len(self.entries),
            "termsCheckedOn": terms.checked_on,
            "note": self.note,
        }


class RankingSource(Protocol):
    """출처 어댑터가 지켜야 하는 표면. 수집 실행과 dry run이 같은 정보를 읽는다."""

    source_id: str
    source_label: str
    terms: TermsCheck
    categories: dict[str, CategorySpec]
    remote: bool

    def targets(self, keys: Sequence[str]) -> list[CategorySpec]:
        """요청한 분류의 호출 대상. 네트워크를 부르지 않는다."""
        ...

    def collect(
        self,
        specs: Sequence[CategorySpec],
        *,
        fetcher: Any,
        retrieved_at: str,
    ) -> list[CollectedList]:
        """분류마다 문서를 받아 목록으로 바꾼다. `fetcher`는 원격 출처만 쓴다."""
        ...
