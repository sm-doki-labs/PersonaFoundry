"""수집 실행과 호출 계획(dry run) (P-14, P-21).

기본은 계획 출력뿐이다. 실제 수집은 통합 단계에서 사용자 지시를 받은 뒤 실행한다.
이 모듈은 파일을 쓰지 않는다. 결과를 남길 곳은 저장소가 아니라 `runs/`다.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from acf.collectors.errors import CollectionConfigError, CollectionNotAllowed, NoMatchingList
from acf.collectors.http import FetchSettings, HttpFetcher
from acf.collectors.port import CategorySpec, CollectedList, Gender, RankingSource, TermsCheck
from acf.contracts.reference import RankingScope
from acf.stages.s1_reference.ranking import load_ranking

RECORD_VERSION = "ranking-collection-v0"

# 기본 분류: 성별이 나뉜 두 목록. 혼성 목록(`actor`)은 성별 범위가 있는 캐릭터에 쓰지 않는다.
DEFAULT_CATEGORIES = ("idolFemale", "idolMale")


def now_utc() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class CollectRequest:
    """무엇을, 어떤 성별 범위로 수집할지."""

    scope: RankingScope
    categories: tuple[str, ...] = DEFAULT_CATEGORIES


@dataclass
class CollectedRanking:
    """수집 결과. `document()`가 `popularity-ranking-v2` 검증을 통과한 사전을 돌려준다."""

    source_id: str
    source_label: str
    terms: TermsCheck
    scope: RankingScope
    lists: list[CollectedList]

    def document(self) -> dict[str, Any]:
        doc = {
            "schemaVersion": "popularity-ranking-v2",
            "scope": self.scope.model_dump(mode="json"),
            "lists": [x.as_contract() for x in self.lists],
            "notes": self._notes(),
        }
        load_ranking(doc)  # 형식이 틀리면 ValidationFailed
        return doc

    def _notes(self) -> str:
        urls = sorted({x.url for x in self.lists if x.url})
        parts = [
            f"출처: {self.source_label}({', '.join(urls) or '가짜 수집기'})",
            f'이용 조건 확인 {self.terms.checked_on}: robots "{self.terms.robots_rule}" / '
            f"약관 {self.terms.terms_note}",
        ]
        if self.terms.human_review:
            parts.append("사람 확인 필요: " + " / ".join(self.terms.notes))
        stamps = sorted({x.retrieved_at for x in self.lists})
        parts.append(f"수집 시각 {', '.join(stamps)}")
        return "\n".join(parts)


def select_lists(lists: list[CollectedList], gender: Gender) -> list[CollectedList]:
    """요청한 성별과 같은 분류만 남긴다. 혼성(`any`) 목록은 `any` 범위에서만 쓴다."""
    picked = [x for x in lists if x.gender == gender]
    if not picked:
        have = ", ".join(sorted({x.gender for x in lists})) or "없음"
        raise NoMatchingList(
            f"요청한 성별({gender})의 목록이 수집 결과에 없다(받은 분류: {have})."
            " 출처가 그 분류를 공개하지 않으면 다른 출처를 찾는다(P-21)"
        )
    return picked


def _record(
    source: RankingSource,
    lists: list[CollectedList],
    specs: list[CategorySpec],
    stamp: str,
    settings: FetchSettings,
) -> dict[str, Any]:
    return {
        "schemaVersion": RECORD_VERSION,
        "source": {"id": source.source_id, "label": source.source_label},
        "terms": source.terms.as_record(),
        "fetchedAt": stamp,
        "requested": [{"category": s.key, "url": s.url} for s in specs],
        "settings": {
            "userAgent": settings.user_agent,
            "minIntervalS": settings.min_interval_s,
            "timeoutS": settings.timeout_s,
            "retries": settings.retries,
            "backoffS": settings.backoff_s,
        },
        "lists": [x.as_record(source.terms) for x in lists],
    }


def collect_ranking(
    source: RankingSource,
    request: CollectRequest,
    *,
    settings: FetchSettings | None = None,
    fetcher: HttpFetcher | None = None,
    retrieved_at: str | None = None,
) -> tuple[CollectedRanking, dict[str, Any]]:
    """출처를 호출해 계약 문서와 수집 기록을 만든다. 이용 조건이 금지면 아무것도 부르지 않는다."""
    if not source.terms.allowed:
        raise CollectionNotAllowed(
            f"{source.source_label}의 이용 조건이 자동 수집을 허용하지 않는다"
            f"(확인 {source.terms.checked_on}). 다른 출처를 찾는다(P-21)"
        )
    specs = source.targets(request.categories)
    stamp = retrieved_at or now_utc()
    owned = False
    if source.remote and fetcher is None:
        fetcher = HttpFetcher(settings)
        owned = True
    try:
        lists = source.collect(specs, fetcher=fetcher, retrieved_at=stamp)
    finally:
        if owned and fetcher is not None:
            fetcher.close()
    chosen = select_lists(lists, request.scope.characterGender)
    used = fetcher.settings if fetcher is not None else (settings or FetchSettings())
    record = _record(source, chosen, specs, stamp, used)
    result = CollectedRanking(
        source_id=source.source_id,
        source_label=source.source_label,
        terms=source.terms,
        scope=request.scope,
        lists=chosen,
    )
    return result, record


def plan_collection(
    source: RankingSource,
    request: CollectRequest,
    *,
    settings: FetchSettings | None = None,
) -> str:
    """어떤 URL을 몇 번 부를지, 어떤 조건으로 부를지 출력한다. 네트워크를 부르지 않는다."""
    terms = source.terms
    specs = source.targets(request.categories)
    if not specs:
        raise CollectionConfigError("수집할 분류가 비었다")
    s = settings or FetchSettings()
    gap_total = s.min_interval_s * max(len(specs) - 1, 0)
    worst = len(specs) * s.timeout_s * (s.retries + 1) + gap_total
    lines = [
        "순위 수집 호출 계획 (dry run; 실제 수집은 사용자 지시 뒤에만 한다)",
        f"출처: {source.source_label} ({source.source_id})",
        f"이용 조건: robots {terms.robots_url} → {terms.robots_rule} (확인 {terms.checked_on})",
        f"  약관: {terms.terms_url or '확인한 이용약관 페이지 없음'} → {terms.terms_note}",
    ]
    if not terms.allowed:
        lines.append("  판정: 자동 수집 불가. 실행을 거절한다.")
    elif terms.human_review:
        lines.append("  판정: robots 기준 허용, 사람 확인 필요")
        lines.extend(f"    - {note}" for note in terms.notes)
    else:
        lines.append("  판정: 수집 허용")
    lines.append(
        f"요청 {len(specs)}회 · 간격 {s.min_interval_s}초 · 타임아웃 {s.timeout_s}초 · "
        f"재시도 {s.retries}회(최대 {s.retries + 1}회 시도) · User-Agent {s.user_agent}"
    )
    for i, spec in enumerate(specs, 1):
        target = spec.url or "(가짜 수집기: 요청 없음)"
        lines.append(f"  {i}. {target} → {spec.label} ({spec.gender})")
    lines.append(f"예상 소요: 최소 {gap_total:.0f}초, 최악 {worst:.0f}초")
    lines.append(
        f"범위: 캐릭터 성별 {request.scope.characterGender} · {request.scope.ageRange} · "
        f"{request.scope.artStyle} · 인물 인상 {request.scope.appearanceOrigin}"
    )
    lines.append(
        "기록: 목록마다 출처 URL·수집 시각·이용 조건 확인 날짜를 남긴다(저장 위치는 runs/)."
    )
    return "\n".join(lines)
