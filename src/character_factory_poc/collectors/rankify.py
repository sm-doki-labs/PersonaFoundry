"""랭키파이(rankify.site) 월간 순위 어댑터 (P-14, P-21, Q-0013).

한국기업평판연구소 브랜드평판지수를 인용해 월간으로 공개하는 사이트다. robots.txt가 모든
User-Agent에 허용(`Allow: /`)이고, 페이지는 서버가 그린 HTML에 `li.rank-item` 목록과
`schema.org ItemList` JSON-LD를 함께 담는다. 그래서 HTML 표를 읽는다.

원자료(브랜드평판지수)의 재사용 조건은 이 사이트 문서만으로 판단할 수 없다. 확인 기록에
`human_review=True`로 남기고, 통합 전에 사람이 한 번 더 본다
(docs/research/2026-10-27-ranking-sources.md).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from html.parser import HTMLParser
from typing import Any

from character_factory_poc.collectors.errors import CollectionConfigError, CollectionParseError
from character_factory_poc.collectors.port import CategorySpec, CollectedList, TermsCheck
from character_factory_poc.contracts.reference import RankingEntry

SLUG = "rankify"
SOURCE = "랭키파이(rankify.site)"

# 발표 형식·분류는 2026-10-27에 확인한 화면 기준이다. 화면이 바뀌면 이 표를 고친다.
CATEGORIES: dict[str, CategorySpec] = {
    "idolFemale": CategorySpec(
        key="idolFemale",
        slug="idol-female",
        label="여자 아이돌",
        gender="female",
        url="https://rankify.site/idolFemale",
    ),
    "idolMale": CategorySpec(
        key="idolMale",
        slug="idol-male",
        label="남자 아이돌",
        gender="male",
        url="https://rankify.site/idolMale",
    ),
    # 연간 순위(2026-11-07 확인). 월간 목록이 10명뿐이라 외모군을 만들 인원을 늘리는 데 쓴다.
    "idolFemale2026": CategorySpec(
        key="idolFemale2026",
        slug="idol-female-2026",
        label="여자 아이돌(2026 연간)",
        gender="female",
        url="https://rankify.site/idolFemale2026",
    ),
    "idolFemale2025": CategorySpec(
        key="idolFemale2025",
        slug="idol-female-2025",
        label="여자 아이돌(2025 연간)",
        gender="female",
        url="https://rankify.site/idolFemale2025",
    ),
    "idolMale2026": CategorySpec(
        key="idolMale2026",
        slug="idol-male-2026",
        label="남자 아이돌(2026 연간)",
        gender="male",
        url="https://rankify.site/idolMale2026",
    ),
    "idolMale2025": CategorySpec(
        key="idolMale2025",
        slug="idol-male-2025",
        label="남자 아이돌(2025 연간)",
        gender="male",
        url="https://rankify.site/idolMale2025",
    ),
    "actor": CategorySpec(
        key="actor",
        # 배우 순위는 성별을 나누지 않는다. `any`로 두어 성별 범위가 섞이지 않게 한다.
        slug="actor",
        label="배우(혼성)",
        gender="any",
        url="https://rankify.site/actor",
    ),
}

TERMS = TermsCheck(
    checked_on="2026-10-27",
    robots_url="https://rankify.site/robots.txt",
    robots_rule="User-agent: * / Allow: / (Sitemap: https://rankify.site/sitemap.xml)",
    robots_allows=True,
    terms_url="",
    terms_note=(
        "이용약관 페이지 없음(/terms는 404). 개인정보처리방침만 있고 자동 접근 제한 문구는 없다"
    ),
    terms_allows=None,
    human_review=True,
    notes=(
        "지수 원자료는 한국기업평판연구소 브랜드평판지수 인용이다. "
        "원자료 재사용 조건은 사람이 확인한다.",
        "사이트는 상위 5위만 실측이고 나머지는 공표된 순위에 맞춘 추정치라고 밝힌다.",
        "배우 순위는 혼성이다. 성별 범위가 있는 캐릭터에는 아이돌 분류만 쓴다.",
    ),
)

LIST_NOTE = "출처 표기: 상위 5위만 실측, 나머지는 공표 순위에 맞춘 추정치(랭키파이 안내)."

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
_YEAR_MONTH = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
_YEAR = re.compile(r"(\d{4})\s*년")
_LD_JSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)

# 목록 항목에서 뽑을 칸의 class 이름과 기록 키.
_FIELDS = {
    "rank-pos": "rank",
    "rank-name": "name",
    "rank-cat": "category",
    "mau-num": "score",
}


class _RankListParser(HTMLParser):
    """`li.rank-item` 안의 순위·이름·분류·지수를 읽는다. 태그 구조가 아니라 class로 찾는다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._li_depth = 0
        self._capture: str | None = None
        self._capture_tag = ""
        self._capture_depth = 0
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "li" and "rank-item" in classes:
            self._current = {}
            self._li_depth = 1
            return
        if self._current is None:
            return
        if tag == "li":
            self._li_depth += 1
        if self._capture is not None:
            if tag == self._capture_tag:
                self._capture_depth += 1
            return
        for css, key in _FIELDS.items():
            if css in classes:
                self._capture, self._capture_tag, self._capture_depth = key, tag, 1
                self._buffer = []
                return

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if self._capture is not None and tag == self._capture_tag:
            self._capture_depth -= 1
            if self._capture_depth == 0:
                self._current[self._capture] = "".join(self._buffer).strip()
                self._capture, self._capture_tag, self._buffer = None, "", []
        if tag == "li":
            self._li_depth -= 1
            if self._li_depth == 0:
                self.items.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._capture is not None:
            self._buffer.append(data)


def _period_of(title: str, url: str) -> str:
    """제목에서 발표 기간을 만든다. `2026년 9월` → `2026-09`, `2026년` → `2026`."""
    m = _YEAR_MONTH.search(title)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = _YEAR.search(title)
    if m:
        return f"{int(m.group(1)):04d}"
    raise CollectionParseError(f"{url}: 발표 기간(연·월)을 제목에서 찾지 못했다")


def _score_of(text: Any) -> float | None:
    if not isinstance(text, str):
        return None
    digits = re.sub(r"[^0-9.]", "", text)
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _from_json_ld(html: str) -> list[tuple[int, str]]:
    """JSON-LD `ItemList`에서 (순위, 이름)을 읽는다. 표 구조가 바뀌었을 때의 대비책이다."""
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for doc in candidates:
            if not isinstance(doc, dict):
                continue
            items = doc.get("itemListElement")
            if not isinstance(items, list) or not items:
                continue
            found: list[tuple[int, str]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    pos = int(item.get("position"))
                except (TypeError, ValueError):
                    continue
                name = str(item.get("name") or "").strip()
                if name:
                    found.append((pos, name))
            if found:
                return found
    return []


def parse_rank_page(html: str, *, url: str) -> tuple[str, list[RankingEntry]]:
    """문서 하나에서 발표 기간과 순위 항목을 뽑는다. 항목이 없으면 `CollectionParseError`."""
    parser = _RankListParser()
    parser.feed(html)
    entries: list[RankingEntry] = []
    for item in parser.items:
        try:
            rank = int(str(item.get("rank", "")).strip())
        except ValueError:
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        entries.append(RankingEntry(rank=rank, name=name, score=_score_of(item.get("score"))))

    if not entries:
        fallback = _from_json_ld(html)
        entries = [RankingEntry(rank=pos, name=name) for pos, name in fallback]
    if not entries:
        raise CollectionParseError(f"{url}: 순위 항목을 찾지 못했다(화면 구조가 바뀌었을 수 있다)")

    ranks = [e.rank for e in entries]
    if len(set(ranks)) != len(ranks):
        raise CollectionParseError(f"{url}: 같은 순위가 두 번 나온다")
    entries.sort(key=lambda e: e.rank)

    match = _TITLE.search(html)
    title = re.sub(r"\s+", " ", match.group(1)) if match else ""
    return _period_of(title, url), entries


class RankifySource:
    """랭키파이 월간 순위. 분류마다 페이지 하나를 부른다."""

    source_id = SLUG
    source_label = SOURCE
    terms = TERMS
    categories = CATEGORIES
    remote = True

    def targets(self, keys: Sequence[str]) -> list[CategorySpec]:
        specs: list[CategorySpec] = []
        for key in keys:
            spec = self.categories.get(key)
            if spec is None:
                known = ", ".join(sorted(self.categories))
                raise CollectionConfigError(f"모르는 분류다: {key} (가능: {known})")
            specs.append(spec)
        return specs

    def list_id(self, spec: CategorySpec, period: str) -> str:
        return f"{SLUG}-{spec.slug}-{period}"

    def collect(
        self,
        specs: Sequence[CategorySpec],
        *,
        fetcher: Any,
        retrieved_at: str,
    ) -> list[CollectedList]:
        if fetcher is None:
            raise CollectionConfigError("원격 출처는 HttpFetcher가 필요하다")
        collected: list[CollectedList] = []
        for spec in specs:
            outcome = fetcher.fetch(spec.key, spec.url)
            period, entries = parse_rank_page(outcome.text, url=spec.url)
            collected.append(
                CollectedList(
                    list_id=self.list_id(spec, period),
                    source=SOURCE,
                    category=spec.label,
                    period=period,
                    gender=spec.gender,
                    url=spec.url,
                    retrieved_at=retrieved_at,
                    entries=entries,
                    note=LIST_NOTE,
                )
            )
        return collected
