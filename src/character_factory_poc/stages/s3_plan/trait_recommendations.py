"""Small, transparent lexical recommendations over a portable authored-behavior library."""

from __future__ import annotations

import re
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.creator_traits import CreatorTrait

CATALOG_PATH = Path(__file__).parents[2] / "resources" / "creator-traits-v1.json"
# Search vocabulary, not a psychological mapping or personality diagnosis.
ALIASES = (
    (("다정", "친절", "배려", "따뜻", "공감"), ("살피", "챙", "도움", "안심", "기분", "듣")),
    (("조용", "무뚝뚝", "내향", "말수"), ("혼자", "말을 아", "먼저 듣", "짧게", "조용")),
    (("장난", "유쾌", "엉뚱", "재미"), ("장난", "농담", "즐", "상상", "재미")),
    (("계획", "꼼꼼", "성실", "책임"), ("약속", "세부", "확인", "끝", "계획", "책임")),
    (
        ("자존심", "독립", "단호", "솔직"),
        ("자기 요구", "자기 시간", "거절", "한계", "불리", "분명"),
    ),
    (("소심", "불안", "예민", "걱정"), ("불안", "걱정", "조심", "위험", "신호")),
    (("즉흥", "활발", "외향", "적극"), ("먼저", "제안", "사람", "시도", "움직")),
)


def load_catalog(path: Path | None = None) -> dict:
    path = path or CATALOG_PATH
    data = read_json(path)
    if data.get("schemaVersion") != "creator-trait-catalog-v1":
        raise ValueError("지원하지 않는 특질 카탈로그입니다.")
    items = data.get("items", [])
    if not items or len({x["traitId"] for x in items}) != len(items):
        raise ValueError("특질 카탈로그가 비어 있거나 ID가 중복되었습니다.")
    digest = sha256_file(path)
    data["catalogSha256"] = digest
    data["totalTraits"] = len(items)
    data["totalPresets"] = len({x["presetId"] for x in items})
    for item in items:
        _snapshot(item, data)  # Validate the portable projection before exposing it.
    return data


def _snapshot(item: dict, catalog: dict) -> CreatorTrait:
    return CreatorTrait(
        **{k: item[k] for k in ("traitId", "behavior", "presetId", "sourceField")},
        catalogSha256=catalog["catalogSha256"],
        sourceCatalogSha256=catalog["source"]["sha256"],
    )


def resolve_traits(ids, *, catalog_sha=None, catalog=None) -> list[CreatorTrait]:
    if isinstance(ids, (list, tuple)) and not ids and catalog_sha is None:
        return []  # Optional recommendations cannot make basic-profile saving unavailable.
    catalog = catalog if catalog is not None else load_catalog()
    if catalog_sha is not None and catalog_sha != catalog["catalogSha256"]:
        raise ValueError("특질 카탈로그가 바뀌었습니다. 추천을 새로 불러와 주세요.")
    if not isinstance(ids, (list, tuple)) or any(not isinstance(x, str) for x in ids):
        raise ValueError("선택 특질은 ID 목록이어야 합니다.")
    if len(ids) > 5 or len(ids) != len(set(ids)):
        raise ValueError("추가 특질은 중복 없이 최대 5개까지 선택할 수 있습니다.")
    by_id = {x["traitId"]: x for x in catalog["items"]}
    if any(x not in by_id for x in ids):
        raise ValueError("알 수 없는 특질이 있습니다. 추천을 다시 확인해 주세요.")
    return [_snapshot(by_id[x], catalog) for x in ids]


def verify_selected_traits(selected, *, catalog=None) -> None:
    if not selected:
        return
    catalog = catalog if catalog is not None else load_catalog()
    expected = resolve_traits([x.traitId for x in selected], catalog=catalog)
    if selected != expected:
        raise ValueError("선택 특질의 원문 또는 출처가 카탈로그와 다릅니다.")


def catalog_view(catalog=None) -> dict:
    catalog = catalog if catalog is not None else load_catalog()
    return {
        "catalogSha256": catalog["catalogSha256"],
        "totalTraits": catalog["totalTraits"],
        "totalPresets": catalog["totalPresets"],
        "items": [dump(_snapshot(item, catalog)) for item in catalog["items"]],
    }


def _words(text):
    return set(re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower()))


def recommend_traits(
    personality, *, selected_ids=(), dismissed_ids=(), search="", limit=5, catalog=None
) -> dict:
    if not isinstance(personality, str) or len(personality) > 5000:
        raise ValueError("성격 설명은 5,000자 이내로 입력해 주세요.")
    if not isinstance(search, str) or len(search) > 200:
        raise ValueError("검색어는 200자 이내로 입력해 주세요.")
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("추천 개수는 1~5여야 합니다.")
    catalog = catalog if catalog is not None else load_catalog()
    resolve_traits(selected_ids, catalog=catalog)
    if not isinstance(dismissed_ids, (list, tuple)) or any(
        not isinstance(x, str) for x in dismissed_ids
    ):
        raise ValueError("숨긴 특질은 ID 목록이어야 합니다.")
    excluded = set(selected_ids) | set(dismissed_ids)
    words = _words(personality)
    aliases = {
        term for keys, terms in ALIASES if any(key in personality for key in keys) for term in terms
    }
    query = _words(search)
    ranked = []
    for item in catalog["items"]:
        behavior = item["behavior"]
        if item["traitId"] in excluded or behavior in personality:
            continue
        if search.strip() and not all(word in behavior.lower() for word in query):
            continue
        overlap = sum(term in behavior for term in aliases)
        overlap += 2 * sum(word in behavior for word in words)
        ranked.append((overlap, item))
    ranked.sort(key=lambda row: (-row[0], row[1]["traitId"]))
    matched = any(score > 0 for score, _ in ranked)
    # Spread recommendations across source presets and leave room for a contrast behavior.
    chosen = []
    seen_presets = set()
    if matched and not search.strip() and limit >= 3:
        support = [(s, x) for s, x in ranked if s > 0 and x["role"] != "contrast"]
        contrast = [(s, x) for s, x in ranked if x["role"] == "contrast"]
        pool = support[: max(1, limit - 2)] + contrast[:1] + ranked
    else:
        pool = ranked
    seen_ids = set()
    seen_families = set()
    for score, item in pool:
        if item["traitId"] in seen_ids or item["presetId"] in seen_presets:
            continue
        category = (
            "explore"
            if not matched or score == 0
            else "contrast"
            if item["role"] == "contrast"
            else "reinforce"
        )
        family = (category, item["domain"])
        if family in seen_families:
            continue
        seen_families.add(family)
        seen_ids.add(item["traitId"])
        seen_presets.add(item["presetId"])
        reason = {
            "reinforce": "입력한 성격과 연결되는 표현이 있습니다. 행동으로 보완할지 살펴보세요.",
            "contrast": "프리셋의 대비 성향입니다. 기본 성격과 함께 드러낼 상황을 확인해 주세요.",
            "explore": "추가로 살펴볼 행동 성향입니다. 어울리는지 직접 확인해 주세요.",
        }[category]
        chosen.append(dict(dump(_snapshot(item, catalog)), category=category, reason=reason))
        if len(chosen) == limit:
            break
    return {
        "catalogSha256": catalog["catalogSha256"],
        "totalTraits": catalog["totalTraits"],
        "totalPresets": catalog["totalPresets"],
        "method": "lexical-v1",
        "matchStatus": "matched" if matched else "limited",
        "items": chosen,
    }
