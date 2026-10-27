"""S1 Scout 특징 태깅: 입력·검사·계약 예시 (LLD §8.1 features, FR-06, FR-35).

에이전트의 ./check.sh와 러너가 같은 check_features를 쓴다(checks/registry.py).
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from acf.common.names import find_name_leaks
from acf.contracts.reference import (
    ALL_FIELDS,
    MULTI_FIELDS,
    SINGLE_FIELDS,
    AppearanceFeatures,
    RankingPeople,
)

UNKNOWN = "unknown"
MIN_KNOWN_SINGLE = 4


def load_vocab() -> dict[str, Any]:
    text = resources.files("acf.resources").joinpath("appearance-tag-vocab-v1.json")
    return json.loads(text.read_text("utf-8"))


def scout_people_input(people: RankingPeople) -> list[dict[str, Any]]:
    """Scout에 주는 인물 목록. 순위 수치는 빼고 이름과 분류만 준다."""
    return [
        {
            "personId": p.personId,
            "name": p.name,
            "categories": sorted({a.category for a in p.appearances}),
        }
        for p in people.people
    ]


def check_features(people: list[dict[str, Any]], vocab: dict[str, Any]):
    ids = [p["personId"] for p in people]
    names = [p["name"] for p in people]
    single = vocab.get("single", {})
    multi = vocab.get("multi", {})
    max_multi = int(vocab.get("maxMulti", 3))

    def _check(out: AppearanceFeatures) -> list[str]:
        p: list[str] = []
        if out.vocabVersion != vocab.get("schemaVersion"):
            p.append(f"vocabVersion: '{vocab.get('schemaVersion')}'을 그대로 쓴다")
        seen = [f.personId for f in out.features]
        missing = [i for i in ids if i not in seen]
        extra = sorted({i for i in seen if i not in ids})
        dup = sorted({i for i in seen if seen.count(i) > 1})
        if missing:
            p.append("features: 빠진 personId가 있다: " + ", ".join(missing))
        if extra:
            p.append("features: 입력에 없는 personId: " + ", ".join(extra))
        if dup:
            p.append("features: personId가 두 번 이상 나온다: " + ", ".join(dup))
        for f in out.features:
            pid = f.personId
            known = 0
            for field in SINGLE_FIELDS:
                v = getattr(f.tags, field)
                allowed = single.get(field, {}).get("values", {})
                if v == UNKNOWN:
                    continue
                if v not in allowed:
                    p.append(
                        f"{pid}.tags.{field}: '{v}'는 어휘에 없다. "
                        f"허용 값: {', '.join(allowed)} 또는 unknown"
                    )
                else:
                    known += 1
            for field in MULTI_FIELDS:
                vals = getattr(f.tags, field)
                allowed = multi.get(field, {}).get("values", {})
                bad = [v for v in vals if v not in allowed]
                if bad:
                    p.append(
                        f"{pid}.tags.{field}: 어휘에 없는 값 {', '.join(bad)}. "
                        f"허용 값: {', '.join(allowed)}"
                    )
                if len(vals) > max_multi:
                    p.append(f"{pid}.tags.{field}: {max_multi}개 이하로 고른다")
                if len(set(vals)) != len(vals):
                    p.append(f"{pid}.tags.{field}: 같은 값을 두 번 쓰지 않는다")
                if f.recognized and not vals:
                    p.append(f"{pid}.tags.{field}: recognized=true면 하나 이상 고른다")
            if f.recognized and known < MIN_KNOWN_SINGLE:
                p.append(
                    f"{pid}: recognized=true면 단일값 필드 {MIN_KNOWN_SINGLE}개 이상을 어휘 값으로 채운다"
                    "(모르면 recognized=false)"
                )
            bad_keys = sorted(k for k in f.confidence if k not in ALL_FIELDS)
            if bad_keys:
                p.append(f"{pid}.confidence: 필드 이름이 아닌 키 {', '.join(bad_keys)}")
            if find_name_leaks(f.note, names):
                p.append(f"{pid}.note: 인물 이름을 쓰지 않는다(FR-35)")
        if find_name_leaks(out.notes, names):
            p.append("notes: 인물 이름을 쓰지 않는다(FR-35)")
        return p

    return _check


def contract_example(people: list[dict[str, Any]], vocab: dict[str, Any]) -> dict[str, Any]:
    single = vocab["single"]
    multi = vocab["multi"]

    def first(d: dict[str, Any], field: str) -> str:
        return next(iter(d[field]["values"]))

    pid = people[0]["personId"] if people else "p001"
    return {
        "schemaVersion": "appearance-features-v1",
        "vocabVersion": vocab["schemaVersion"],
        "features": [
            {
                "personId": pid,
                "recognized": True,
                "tags": {
                    **{f: first(single, f) for f in SINGLE_FIELDS},
                    "hairColor": UNKNOWN,
                    **{f: [first(multi, f)] for f in MULTI_FIELDS},
                },
                "confidence": {f: 0.8 for f in ALL_FIELDS} | {"hairColor": 0.3},
                "note": "<불확실한 점. 이름은 쓰지 않는다>",
            },
            {
                "personId": "<모르는 인물의 personId>",
                "recognized": False,
                "tags": {**{f: UNKNOWN for f in SINGLE_FIELDS}, "styling": [], "mood": []},
                "confidence": {},
                "note": "외모를 알지 못한다",
            },
        ],
        "notes": "<전체적으로 불확실했던 점 한두 문장. 이름 없이>",
    }
