"""화제성 순위 수집 (B 갈래, P-14·P-21, Q-0013).

출처 이용 조건을 확인한 어댑터만 `popularity-ranking-v2`를 만든다. 실제 수집은 사용자 지시 뒤
통합 단계에서 하고, 이 패키지의 기본 진입점 `plan_collection`은 호출 계획만 낸다.
"""

from character_factory_poc.collectors.collect import (
    DEFAULT_CATEGORIES,
    RECORD_VERSION,
    CollectedRanking,
    CollectRequest,
    collect_ranking,
    now_utc,
    plan_collection,
    select_lists,
)
from character_factory_poc.collectors.errors import (
    CollectionConfigError,
    CollectionError,
    CollectionNotAllowed,
    CollectionParseError,
    FetchError,
    NoMatchingList,
)
from character_factory_poc.collectors.fake import FakeRankingSource
from character_factory_poc.collectors.http import FetchOutcome, FetchSettings, HttpFetcher
from character_factory_poc.collectors.port import (
    CategorySpec,
    CollectedList,
    Gender,
    RankingSource,
    TermsCheck,
)
from character_factory_poc.collectors.rankify import RankifySource, parse_rank_page

__all__ = [
    "RECORD_VERSION",
    "CategorySpec",
    "CollectRequest",
    "CollectedList",
    "CollectedRanking",
    "CollectionConfigError",
    "CollectionError",
    "CollectionNotAllowed",
    "CollectionParseError",
    "DEFAULT_CATEGORIES",
    "FakeRankingSource",
    "FetchError",
    "FetchOutcome",
    "FetchSettings",
    "Gender",
    "HttpFetcher",
    "NoMatchingList",
    "RankifySource",
    "RankingSource",
    "TermsCheck",
    "collect_ranking",
    "now_utc",
    "parse_rank_page",
    "plan_collection",
    "select_lists",
]
