"""화제성 순위 수집 오류 (B 갈래, P-14·P-21)."""

from __future__ import annotations

from acf.common.errors import FactoryError


class CollectionError(FactoryError):
    """수집 관련 오류의 기반."""


class CollectionNotAllowed(CollectionError):
    """출처의 이용 조건 확인 기록이 자동 수집을 허용하지 않는다."""


class CollectionConfigError(CollectionError):
    """수집 설정(간격·타임아웃·재시도·User-Agent)이 잘못됐다."""


class FetchError(CollectionError):
    """출처 응답을 받지 못했다(HTTP 오류·재시도 소진)."""


class CollectionParseError(CollectionError):
    """출처 문서에서 순위 목록을 읽지 못했다(형식이 바뀌었을 수 있다)."""


class NoMatchingList(CollectionError):
    """요청한 성별 분류가 수집 결과에 없다."""
