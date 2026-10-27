"""화제성 순위 수집 (B 갈래, P-14·P-21): 파싱 → 계약 검증, 성별 분리, dry run, 거절.

합성 HTML/JSON만 쓴다. 실제 순위 목록의 인물 이름과 실제 사이트 응답은 fixture에 넣지 않는다.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from acf.collectors import (
    CollectionConfigError,
    CollectionNotAllowed,
    CollectionParseError,
    CollectRequest,
    FakeRankingSource,
    FetchError,
    FetchSettings,
    HttpFetcher,
    NoMatchingList,
    RankifySource,
    TermsCheck,
    collect_ranking,
    parse_rank_page,
    plan_collection,
)
from acf.contracts.reference import RankingScope
from acf.stages.s1_reference.ranking import load_ranking

FEMALE = ("idolFemale", "idolMale")


def scope(gender: str) -> RankingScope:
    return RankingScope(
        characterGender=gender,  # type: ignore[arg-type]
        ageRange="20s",
        artStyle="photoreal",
        appearanceOrigin="korean",
        moodHints=["차분한"],
    )


def page(title: str, rows: list[tuple[int, str, str, str | None]]) -> str:
    """랭키파이 화면과 같은 class 구조의 합성 문서. 이름은 전부 가상이다."""
    items = []
    for rank, name, cat, score in rows:
        score_html = f'<div class="mau-num">{score}</div>' if score is not None else ""
        items.append(
            f'<li class="rank-item top{rank}"><div class="rank-row">'
            f'<div class="rank-num"><span class="rank-pos">{rank}</span>'
            f'<span class="change up">▲1</span></div>'
            f'<div class="rank-main"><span class="rank-info">'
            f'<span class="rank-name">{name}</span>'
            f'<span class="rank-cat">{cat}</span></span></div>'
            f'<div class="rank-mau">{score_html}</div>'
            f"</div></li>"
        )
    return (
        "<html><head>"
        f"<title>{title} | 랭키파이</title>"
        "</head><body><main>"
        f'<ol class="rank-list">{"".join(items)}</ol>'
        "</main></body></html>"
    )


FEMALE_PAGE = page(
    "2026년 9월 K-POP 여자 아이돌 순위 TOP 3",
    [
        (1, "가상 하나", "가상기획", "9,000,000"),
        (2, "가상 두리", "가상기획", "8,000,000"),
        (3, "가상 세아", "드라마", None),
    ],
)
MALE_PAGE = page(
    "2026년 9월 K-POP 남자 아이돌 순위 TOP 3",
    [
        (1, "가상 마루", "가상기획", "7,500,000"),
        (2, "가상 바다", "가상기획", "6,500,000"),
        (3, "가상 사온", "가상기획", "5,500,000"),
    ],
)

URLS = {
    "https://rankify.site/idolFemale": FEMALE_PAGE,
    "https://rankify.site/idolMale": MALE_PAGE,
}


def serving(seen: list[str], pages: dict[str, str] | None = None) -> httpx.MockTransport:
    """URL별 합성 응답. 어떤 URL을 불렀는지 `seen`에 남긴다."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        body = (pages or URLS).get(str(request.url))
        if body is None:
            return httpx.Response(404, text="없는 페이지")
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    return httpx.MockTransport(handler)


class FakeClock:
    """테스트용 시간. `sleep`이 시간을 밀어 실제로 기다리지 않는다."""

    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.t += seconds


def fetcher(transport: httpx.Transport, clock: FakeClock, **over: Any) -> HttpFetcher:
    settings = FetchSettings.from_mapping(
        {"min_interval_s": 5.0, "timeout_s": 10.0, "retries": 2, "backoff_s": 1.0} | over
    )
    return HttpFetcher(
        settings,
        client=httpx.Client(transport=transport, timeout=settings.timeout_s),
        sleep=clock.sleep,
        clock=clock.monotonic,
    )


def test_parse_rank_page_reads_period_rank_and_score() -> None:
    period, entries = parse_rank_page(FEMALE_PAGE, url="https://rankify.site/idolFemale")
    assert period == "2026-09"
    assert [e.rank for e in entries] == [1, 2, 3]
    assert [e.name for e in entries] == ["가상 하나", "가상 두리", "가상 세아"]
    assert entries[0].score == 9_000_000.0
    assert entries[2].score is None


def test_parse_rank_page_falls_back_to_json_ld() -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "numberOfItems": 2,
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "가상 라온"},
            {"@type": "ListItem", "position": 2, "name": "가상 미르"},
        ],
    }
    html = (
        "<html><head><title>2026년 10월 배우 순위</title>"
        f'<script type="application/ld+json">{json.dumps(payload)}</script>'
        "</head><body><p>자리 표시</p></body></html>"
    )
    period, entries = parse_rank_page(html, url="https://example.invalid/a")
    assert period == "2026-10"
    assert [e.name for e in entries] == ["가상 라온", "가상 미르"]


def test_parse_rank_page_rejects_unknown_layout() -> None:
    with pytest.raises(CollectionParseError) as err:
        parse_rank_page("<html><body>화면이 바뀌었다</body></html>", url="https://example.invalid")
    assert "순위 항목을 찾지 못했다" in str(err.value)


def test_parse_keeps_text_inside_nested_markup() -> None:
    html = (
        "<html><head><title>2026년 9월 여자 아이돌</title></head><body>"
        '<ol class="rank-list"><li class="rank-item">'
        '<span class="rank-pos">1</span>'
        '<span class="rank-name"><span class="hl">가상</span> 하나</span>'
        "</li></ol></body></html>"
    )
    _, entries = parse_rank_page(html, url="https://example.invalid")
    assert entries[0].name == "가상 하나"


def test_parse_rank_page_rejects_duplicate_rank() -> None:
    html = page("2026년 9월 여자 아이돌", [(1, "가상 하나", "가상기획", None)])
    dup = html.replace(
        "</ol>",
        '<li class="rank-item"><span class="rank-pos">1</span>'
        '<span class="rank-name">가상 두리</span></li></ol>',
    )
    with pytest.raises(CollectionParseError) as err:
        parse_rank_page(dup, url="https://example.invalid")
    assert "같은 순위" in str(err.value)


def test_dry_run_plans_requests_without_network() -> None:
    seen: list[str] = []
    text = plan_collection(
        RankifySource(),
        CollectRequest(scope=scope("female"), categories=FEMALE),
        settings=FetchSettings.from_mapping({"min_interval_s": 5.0}),
    )
    assert "요청 2회" in text
    assert "https://rankify.site/idolFemale" in text
    assert "https://rankify.site/idolMale" in text
    assert "재시도 2회" in text
    assert "acf-rankings" in text
    assert "사람 확인 필요" in text
    assert "2026-10-27" in text  # 이용 조건 확인 날짜
    assert seen == []


def test_dry_run_marks_disallowed_source() -> None:
    source = FakeRankingSource()
    source.terms = TermsCheck(
        checked_on="2026-10-27",
        robots_url="https://example.invalid/robots.txt",
        robots_rule="User-agent: * / Disallow: /",
        robots_allows=False,
        terms_url="https://example.invalid/terms",
        terms_note="자동 수집 금지",
        terms_allows=False,
    )
    text = plan_collection(source, CollectRequest(scope=scope("female"), categories=FEMALE))
    assert "자동 수집 불가" in text


def test_disallowed_source_is_refused_before_any_request() -> None:
    seen: list[str] = []
    clock = FakeClock()
    source = FakeRankingSource()
    source.terms = TermsCheck(
        checked_on="2026-10-27",
        robots_url="https://example.invalid/robots.txt",
        robots_rule="User-agent: * / Disallow: /",
        robots_allows=False,
        terms_url="",
        terms_note="이용약관이 재사용을 금지한다",
        terms_allows=False,
    )
    with pytest.raises(CollectionNotAllowed) as err:
        collect_ranking(
            source,
            CollectRequest(scope=scope("female"), categories=FEMALE),
            fetcher=fetcher(serving(seen), clock),
        )
    assert "허용하지 않는다" in str(err.value)
    assert seen == []


def test_collect_female_scope_keeps_only_female_list() -> None:
    seen: list[str] = []
    clock = FakeClock()
    result, record = collect_ranking(
        RankifySource(),
        CollectRequest(scope=scope("female"), categories=FEMALE),
        fetcher=fetcher(serving(seen), clock),
        retrieved_at="2026-10-27T00:00:00Z",
    )
    doc = result.document()
    load_ranking(doc)  # 계약 검증을 한 번 더 명시적으로 확인한다.
    assert len(doc["lists"]) == 1
    assert doc["lists"][0]["listId"] == "rankify-idol-female-2026-09"
    assert doc["lists"][0]["category"] == "여자 아이돌"
    assert doc["lists"][0]["retrievedAt"] == "2026-10-27T00:00:00Z"
    names = [e["name"] for e in doc["lists"][0]["entries"]]
    assert names == ["가상 하나", "가상 두리", "가상 세아"]
    assert "score" not in doc["lists"][0]["entries"][2]
    assert len(seen) == 2
    assert record["lists"][0]["gender"] == "female"


def test_collect_male_scope_keeps_only_male_list() -> None:
    seen: list[str] = []
    result, record = collect_ranking(
        RankifySource(),
        CollectRequest(scope=scope("male"), categories=FEMALE),
        fetcher=fetcher(serving(seen), FakeClock()),
        retrieved_at="2026-10-27T00:00:00Z",
    )
    doc = result.document()
    assert [x["listId"] for x in doc["lists"]] == ["rankify-idol-male-2026-09"]
    assert doc["scope"]["characterGender"] == "male"
    assert record["lists"][0]["category"] == "남자 아이돌"


def test_collection_record_keeps_source_url_time_and_terms() -> None:
    _, record = collect_ranking(
        RankifySource(),
        CollectRequest(scope=scope("female"), categories=("idolFemale",)),
        fetcher=fetcher(serving([]), FakeClock()),
        retrieved_at="2026-10-27T01:02:03Z",
    )
    assert record["schemaVersion"] == "ranking-collection-v0"
    assert record["terms"]["robotsAllows"] is True
    assert record["terms"]["humanReview"] is True
    assert record["terms"]["checkedOn"] == "2026-10-27"
    assert record["lists"][0]["url"] == "https://rankify.site/idolFemale"
    assert record["lists"][0]["retrievedAt"] == "2026-10-27T01:02:03Z"
    assert record["lists"][0]["termsCheckedOn"] == "2026-10-27"
    assert record["lists"][0]["entryCount"] == 3
    assert record["settings"]["minIntervalS"] == 5.0


def test_document_notes_carry_source_and_time_but_no_terms_detail_leak() -> None:
    result, _ = collect_ranking(
        RankifySource(),
        CollectRequest(scope=scope("female"), categories=("idolFemale",)),
        fetcher=fetcher(serving([]), FakeClock()),
        retrieved_at="2026-10-27T01:02:03Z",
    )
    notes = result.document()["notes"]
    assert "https://rankify.site/idolFemale" in notes
    assert "2026-10-27T01:02:03Z" in notes
    assert "사람 확인 필요" in notes


def test_requests_keep_min_interval() -> None:
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        clock.t += 0.5  # 요청 한 번에 0.5초가 걸린다고 본다.
        return httpx.Response(200, text=URLS[str(request.url)])

    client = HttpFetcher(
        FetchSettings.from_mapping({"min_interval_s": 5.0, "timeout_s": 10.0, "retries": 0}),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=clock.sleep,
        clock=clock.monotonic,
    )
    collect_ranking(
        RankifySource(),
        CollectRequest(scope=scope("female"), categories=FEMALE),
        fetcher=client,
        retrieved_at="2026-10-27T00:00:00Z",
    )
    assert len(clock.sleeps) == 1
    assert 4.0 < clock.sleeps[0] <= 5.0


def test_retry_then_success_records_attempts() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, text="잠시 막힘")
        return httpx.Response(200, text=FEMALE_PAGE)

    clock = FakeClock()
    client = fetcher(httpx.MockTransport(handler), clock)
    outcome = client.fetch("idolFemale", "https://rankify.site/idolFemale")
    assert outcome.status == 200
    assert outcome.attempts == 2
    assert client.waits[0] == 1.0


def test_request_carries_configured_user_agent_and_timeout() -> None:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, text=FEMALE_PAGE)

    client = fetcher(httpx.MockTransport(handler), FakeClock(), user_agent="acf-test/1.0")
    client.fetch("idolFemale", "https://rankify.site/idolFemale")
    assert seen[0]["user-agent"] == "acf-test/1.0"


def test_retry_exhausted_raises_fetch_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="계속 막힘")

    clock = FakeClock()
    client = fetcher(httpx.MockTransport(handler), clock, retries=1)
    with pytest.raises(FetchError) as err:
        client.fetch("idolFemale", "https://rankify.site/idolFemale")
    assert "HTTP 503" in str(err.value)
    assert clock.sleeps[0] == 1.0  # 재시도 전 백오프
    assert len(clock.sleeps) == 2  # 백오프 + 요청 간격


def test_client_error_is_not_retried() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(404, text="없음")

    with pytest.raises(FetchError):
        fetcher(httpx.MockTransport(handler), FakeClock()).fetch("idolFemale", "https://x.invalid")
    assert attempts["n"] == 1


def test_missing_gender_list_reports_other_source_needed() -> None:
    with pytest.raises(NoMatchingList) as err:
        collect_ranking(
            RankifySource(),
            CollectRequest(scope=scope("female"), categories=("actor",)),
            fetcher=fetcher(serving([], {"https://rankify.site/actor": FEMALE_PAGE}), FakeClock()),
            retrieved_at="2026-10-27T00:00:00Z",
        )
    assert "다른 출처를 찾는다" in str(err.value)


def test_unknown_category_is_rejected() -> None:
    with pytest.raises(CollectionConfigError):
        RankifySource().targets(["없는분류"])


def test_fake_source_makes_contract_valid_lists_without_network() -> None:
    result, record = collect_ranking(
        FakeRankingSource(),
        CollectRequest(scope=scope("female"), categories=FEMALE),
        retrieved_at="2026-10-27T00:00:00Z",
    )
    doc = result.document()
    assert doc["lists"][0]["listId"] == "fake-female-2026-10"
    assert all(e["name"].startswith("가상") for e in doc["lists"][0]["entries"])
    assert record["source"]["id"] == "fake"
    assert record["lists"][0]["url"] == ""


def test_list_id_fits_contract_slug() -> None:
    spec = RankifySource().targets(["idolFemale"])[0]
    given = RankifySource().list_id(spec, "2026-09")
    assert given == "rankify-idol-female-2026-09"
    assert len(given) <= 41


def test_settings_are_validated() -> None:
    with pytest.raises(CollectionConfigError):
        FetchSettings.from_mapping({"timeout_s": 0})
    with pytest.raises(CollectionConfigError):
        FetchSettings.from_mapping({"retries": -1})
    with pytest.raises(CollectionConfigError):
        FetchSettings.from_mapping({"user_agent": "  "})
