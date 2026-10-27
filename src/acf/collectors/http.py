"""HTTP 수집 공통부: User-Agent·요청 간격·재시도·타임아웃 (P-14).

기본값은 설정으로 덮어쓴다. 실제 실행은 통합 단계에서 사용자 지시를 받은 뒤에만 하고,
테스트는 `httpx.MockTransport`로 네트워크 없이 돈다(NFR-08).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from acf.collectors.errors import CollectionConfigError, FetchError

DEFAULTS: dict[str, Any] = {
    # 개발 도구임을 밝히고, 연락처 대신 저장소·목적을 적는다.
    "user_agent": "acf-rankings/0.1 (+character-factory PoC; polite crawl)",
    "min_interval_s": 5.0,
    "timeout_s": 20.0,
    "retries": 2,
    "backoff_s": 2.0,
}

# 재시도할 응답. 4xx는 형식·경로가 바뀐 것이므로 바로 실패로 본다.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class FetchSettings:
    """요청 간격·User-Agent·재시도·타임아웃. `factory.toml [collectors.ranking]`에서 읽는다."""

    user_agent: str = DEFAULTS["user_agent"]
    min_interval_s: float = DEFAULTS["min_interval_s"]
    timeout_s: float = DEFAULTS["timeout_s"]
    retries: int = DEFAULTS["retries"]
    backoff_s: float = DEFAULTS["backoff_s"]

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None = None) -> FetchSettings:
        raw = {**DEFAULTS, **dict(data or {})}
        try:
            settings = cls(
                user_agent=str(raw["user_agent"]).strip(),
                min_interval_s=float(raw["min_interval_s"]),
                timeout_s=float(raw["timeout_s"]),
                retries=int(raw["retries"]),
                backoff_s=float(raw["backoff_s"]),
            )
        except (TypeError, ValueError) as e:
            raise CollectionConfigError(f"수집 설정을 읽을 수 없다: {e}") from None
        if not settings.user_agent:
            raise CollectionConfigError("수집 설정 user_agent가 비었다")
        if settings.min_interval_s < 0 or settings.backoff_s < 0:
            raise CollectionConfigError("수집 설정 간격·백오프는 0 이상이어야 한다")
        if settings.timeout_s <= 0:
            raise CollectionConfigError("수집 설정 timeout_s는 0보다 커야 한다")
        if settings.retries < 0:
            raise CollectionConfigError("수집 설정 retries는 0 이상이어야 한다")
        return settings


@dataclass
class FetchOutcome:
    """요청 하나의 결과와 실제 시도 횟수(계획과 대조하기 위해 남긴다)."""

    category_key: str
    url: str
    status: int
    text: str
    attempts: int


class HttpFetcher:
    """httpx 클라이언트 하나로 여러 요청을 순서대로 부르고, 요청 사이 간격을 지킨다."""

    def __init__(
        self,
        settings: FetchSettings | None = None,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.settings = settings or FetchSettings()
        self._client = client
        self._owns_client = client is None
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic
        self._last: float | None = None
        self.outcomes: list[FetchOutcome] = []
        self.waits: list[float] = []

    def __enter__(self) -> HttpFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": self.settings.user_agent},
                timeout=self.settings.timeout_s,
                follow_redirects=True,
            )
        return self._client

    def _wait_turn(self) -> None:
        """직전 요청과 `min_interval_s` 이상 떨어뜨린다. 첫 요청은 기다리지 않는다."""
        if self._last is not None:
            wait = self.settings.min_interval_s - (self._clock() - self._last)
            if wait > 0:
                self.waits.append(round(wait, 3))
                self._sleep(wait)
        self._last = self._clock()

    def _backoff(self, attempt: int) -> None:
        delay = self.settings.backoff_s * attempt
        if delay > 0:
            self.waits.append(round(delay, 3))
            self._sleep(delay)

    def fetch(self, category_key: str, url: str) -> FetchOutcome:
        client = self._ensure_client()
        attempts = 0
        # 클라이언트를 밖에서 받아도 User-Agent는 설정값으로 고정한다.
        headers = {"User-Agent": self.settings.user_agent}
        while True:
            attempts += 1
            self._wait_turn()
            try:
                resp = client.get(url, headers=headers)
            except httpx.HTTPError as e:
                if attempts > self.settings.retries:
                    raise FetchError(
                        f"{url} 요청이 {attempts}번 실패했다({type(e).__name__})"
                    ) from None
                self._backoff(attempts)
                continue
            if resp.status_code in RETRY_STATUS and attempts <= self.settings.retries:
                self._backoff(attempts)
                continue
            if resp.status_code >= 400:
                raise FetchError(f"{url} 응답이 HTTP {resp.status_code}다")
            outcome = FetchOutcome(category_key, url, resp.status_code, resp.text, attempts)
            self.outcomes.append(outcome)
            return outcome
