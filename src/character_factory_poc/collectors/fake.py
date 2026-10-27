"""가짜 순위 수집기 (NFR-08).

네트워크 없이 여성·남성 분류 목록을 돌려준다. 인물 이름은 전부 가상이며, 실제 순위 목록의
이름을 테스트·데모 fixture로 옮기지 않는다(D-0017).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from character_factory_poc.collectors.port import CategorySpec, CollectedList, TermsCheck
from character_factory_poc.contracts.reference import RankingEntry

FAKE_FEMALE = (
    "가상 하나",
    "가상 두리",
    "가상 세아",
    "가상 네음",
    "가상 다올",
)
FAKE_MALE = (
    "가상 마루",
    "가상 바다",
    "가상 사온",
    "가상 아람",
    "가상 자윤",
)

FAKE_TERMS = TermsCheck(
    checked_on="2026-10-27",
    robots_url="(가짜 출처: 해당 없음)",
    robots_rule="가짜 수집기는 네트워크를 부르지 않는다",
    robots_allows=True,
    terms_url="",
    terms_note="가짜 출처라 이용 조건 확인이 필요 없다",
    terms_allows=True,
)


class FakeRankingSource:
    """가짜 출처. `collect`는 fetcher를 쓰지 않고 고정 목록을 만든다."""

    source_id = "fake"
    source_label = "가짜 화제성 순위(테스트)"
    terms = FAKE_TERMS
    remote = False
    categories = {
        "idolFemale": CategorySpec(
            key="idolFemale",
            slug="female",
            label="가상 여성 분류",
            gender="female",
            url="",
        ),
        "idolMale": CategorySpec(
            key="idolMale",
            slug="male",
            label="가상 남성 분류",
            gender="male",
            url="",
        ),
    }

    def __init__(self, period: str = "2026-10") -> None:
        self.period = period

    def targets(self, keys: Sequence[str]) -> list[CategorySpec]:
        return [self.categories[k] for k in keys]

    def list_id(self, spec: CategorySpec, period: str) -> str:
        return f"fake-{spec.slug}-{period}"

    def collect(
        self,
        specs: Sequence[CategorySpec],
        *,
        fetcher: Any,
        retrieved_at: str,
    ) -> list[CollectedList]:
        names = {"female": FAKE_FEMALE, "male": FAKE_MALE}
        collected: list[CollectedList] = []
        for spec in specs:
            pool = names.get(spec.gender, ())
            entries = [
                RankingEntry(rank=i, name=name, score=float(1000 - i * 10))
                for i, name in enumerate(pool, 1)
            ]
            collected.append(
                CollectedList(
                    list_id=self.list_id(spec, self.period),
                    source=self.source_label,
                    category=spec.label,
                    period=self.period,
                    gender=spec.gender,
                    url=spec.url,
                    retrieved_at=retrieved_at,
                    entries=entries,
                    note="가짜 수집기 결과",
                )
            )
        return collected
