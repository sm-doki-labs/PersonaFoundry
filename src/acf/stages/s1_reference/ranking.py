"""S1 순위 목록 고정과 인물 묶기 (LLD §8.1 ranking)."""

from __future__ import annotations

from typing import Any

from acf.common.canonical import sha256_of
from acf.common.errors import ValidationFailed
from acf.common.names import normalize_name
from acf.common.schema import dump, validate
from acf.contracts.reference import PopularityRanking, RankingPeople

RANKING_CONTRACT = "popularity-ranking-v2"


def load_ranking(obj: Any) -> PopularityRanking:
    if isinstance(obj, dict) and obj.get("schemaVersion") == "popularity-ranking-v1":
        raise ValidationFailed(
            RANKING_CONTRACT,
            [
                "schemaVersion: v1 형식이다. scope.appearanceOrigin(korean | east-asian | "
                "unspecified)을 넣고 schemaVersion을 popularity-ranking-v2로 바꾼다(D-0020)"
            ],
        )
    return validate(RANKING_CONTRACT, obj)  # type: ignore[return-value]


def ranking_sha(ranking: PopularityRanking) -> str:
    return sha256_of(dump(ranking))


def percentile(rank: int, size: int, min_size: int) -> float | None:
    """같은 목록 안의 순위 백분위(1위 = 1.0). 목록이 너무 짧으면 None(정규화 불가)."""
    if size < min_size:
        return None
    return round((size - rank + 1) / size, 4)


def build_people(ranking: PopularityRanking, min_list_size: int) -> RankingPeople:
    """목록 순서·순위 순서로 처음 나온 차례대로 personId를 붙이고 같은 이름을 한 사람으로 묶는다."""
    people: dict[str, dict[str, Any]] = {}
    for lst in ranking.lists:
        size = max(len(lst.entries), max(e.rank for e in lst.entries))
        for e in sorted(lst.entries, key=lambda x: x.rank):
            key = normalize_name(e.name)
            if key not in people:
                people[key] = {
                    "personId": f"p{len(people) + 1:03d}",
                    "name": e.name,
                    "appearances": [],
                }
            people[key]["appearances"].append(
                {
                    "listId": lst.listId,
                    "category": lst.category,
                    "rank": e.rank,
                    "listSize": size,
                    "percentile": percentile(e.rank, size, min_list_size),
                }
            )
    return validate(  # type: ignore[return-value]
        "ranking-people-v1",
        {"rankingSha256": ranking_sha(ranking), "people": list(people.values())},
    )


def all_names(ranking: PopularityRanking) -> list[str]:
    return sorted({e.name for lst in ranking.lists for e in lst.entries})
