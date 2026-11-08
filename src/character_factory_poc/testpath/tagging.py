# ruff: noqa: E501  (모델에 보내는 프롬프트 문장은 줄을 나누지 않는다)
"""두 텍스트 모델(GPT·Gemini)로 같은 인물 묶음을 따로 태깅하고 같은 값만 남긴다.

이름은 모델 입력에만 들어간다. 출력·합친 결과·외모군·프롬프트에는 personId만 남는다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.testpath.vocab2 import (
    UNKNOWN,
    all_field_names,
    cluster_multi,
    single_fields,
)

SYSTEM = (
    "너는 캐릭터 공장의 외모 태깅 담당이다. 공개 활동(방송·화보·무대·공식 사진)에서 널리 알려진 "
    "인물의 외모를 정해진 어휘로만 기록한다. 이 기록은 여러 사람이 공유하는 인기 외모 계열을 찾는 "
    "통계에만 쓰이고 특정 인물을 재현하는 데 쓰이지 않는다. 성격·사생활·평가는 쓰지 않는다."
)


def _vocab_listing(vocab: dict[str, Any]) -> str:
    lines = []
    for name, spec in single_fields(vocab).items():
        vals = ", ".join(f"{k}({v['ko']})" for k, v in spec["values"].items())
        lines.append(f"- {name} [{spec['label']}] 하나: {vals}, unknown")
    for name, spec in cluster_multi(vocab).items():
        vals = ", ".join(f"{k}({v['ko']})" for k, v in spec["values"].items())
        lines.append(f"- {name} [{spec['label']}] 1~{vocab['maxMulti']}개 목록: {vals}")
    return "\n".join(lines)


def build_request(people: list[dict[str, Any]], vocab: dict[str, Any], *, ref: str) -> ChatRequest:
    """people: [{personId, name, groups}] 묶음 하나의 태깅 요청."""
    roster = "\n".join(
        f"- {p['personId']}: {p['name']}" + (f" ({p['groups']})" if p.get("groups") else "")
        for p in people
    )
    user = f"""아래 인물마다 최근 공개 활동에서 가장 자주 보이는 모습을 어휘 키로 기록한다.

인물(한국 연예 순위 목록의 여자 아이돌):
{roster}

어휘(키만 쓴다):
{_vocab_listing(vocab)}

규칙:
1. 인물마다 항목 하나. personId는 입력 그대로 쓴다. 이름은 출력에 쓰지 않는다.
2. 그 인물을 확실히 알면 recognized=true. 모르거나 동명이인과 헷갈리면 recognized=false로 두고 모든 단일 칸을 unknown, vibe를 빈 목록으로 둔다. 추측으로 채우지 않는다.
3. gender는 female | male | unknown.
4. 확실하지 않은 단일 칸은 unknown. 머리 길이·색·스타일·앞머리·메이크업처럼 시기마다 바뀌는 칸은 최근 1년에 가장 자주 보인 모습으로 쓰고 확신도를 낮게 준다.
5. confidence에 칸마다 0~1 확신도를 적는다.

JSON만 출력한다:
{{"people": [{{"personId": "p001", "recognized": true, "gender": "female", "tags": {{"<칸>": "<키>", "vibe": ["<키>"]}}, "confidence": {{"<칸>": 0.8}}}}]}}
tags에는 {len(all_field_names(vocab))}개 칸({", ".join(all_field_names(vocab))})을 모두 넣는다."""
    return ChatRequest(
        kind="AGENT",
        stage="testpath-tag",
        messages=(Message("system", SYSTEM), Message("user", user)),
        ref=ref,
        max_output_tokens=32000,
        temperature=0.2,
        response_json=True,
    )


def _json_block(text: str) -> Any:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("응답에서 JSON 객체를 찾지 못했다")
    return json.loads(m.group(0))


def parse_tags(
    text: str, people: list[dict[str, Any]], vocab: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """응답을 personId별 기록으로 바꾼다. 어휘 밖 값은 unknown으로 바꾸고 문제 목록에 남긴다."""
    data = _json_block(text)
    rows = data.get("people") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("people 목록이 없다")
    wanted = {p["personId"] for p in people}
    singles = single_fields(vocab)
    multis = cluster_multi(vocab)
    out: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("personId") not in wanted:
            continue
        pid = row["personId"]
        tags_in = row.get("tags") if isinstance(row.get("tags"), dict) else {}
        conf_in = row.get("confidence") if isinstance(row.get("confidence"), dict) else {}
        tags: dict[str, Any] = {}
        conf: dict[str, float] = {}
        for field, spec in singles.items():
            val = tags_in.get(field, UNKNOWN)
            if val != UNKNOWN and val not in spec["values"]:
                problems.append(f"{pid}.{field}: 어휘 밖 값 {val!r}")
                val = UNKNOWN
            tags[field] = val
        for field, spec in multis.items():
            vals = tags_in.get(field) or []
            vals = vals if isinstance(vals, list) else [vals]
            kept = []
            for v in vals:
                if v in spec["values"] and v not in kept:
                    kept.append(v)
                else:
                    problems.append(f"{pid}.{field}: 어휘 밖 값 {v!r}")
            tags[field] = kept[: int(vocab["maxMulti"])]
        for field in tags:
            try:
                c = float(conf_in.get(field, 0.5))
            except (TypeError, ValueError):
                c = 0.5
            conf[field] = min(1.0, max(0.0, c))
        out[pid] = {
            "recognized": bool(row.get("recognized")),
            "gender": row.get("gender") if row.get("gender") in ("female", "male") else "unknown",
            "tags": tags,
            "confidence": conf,
        }
    missing = sorted(wanted - set(out))
    if missing:
        problems.append(f"빠진 인물: {', '.join(missing)}")
    return out, problems


def cross_check(
    a: dict[str, dict[str, Any]],
    b: dict[str, dict[str, Any]],
    vocab: dict[str, Any],
    *,
    gender: str = "female",
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """두 모델이 모두 알아보고 성별이 맞는 인물만 남기고, 칸마다 같은 값만 남긴다.

    단일 칸: 두 값이 같고 unknown이 아니면 그 값, 아니면 unknown. 복수 칸: 교집합(없으면 빈 목록).
    확신도는 두 모델 중 낮은 값이다.
    """
    singles = single_fields(vocab)
    multis = cluster_multi(vocab)
    merged: dict[str, dict[str, Any]] = {}
    dropped: dict[str, str] = {}
    agree = {f: 0 for f in [*singles, *multis]}
    compared = {f: 0 for f in agree}
    for pid in sorted(set(a) | set(b)):
        x, y = a.get(pid), b.get(pid)
        if x is None or y is None:
            dropped[pid] = "한 모델 응답에 없음"
            continue
        if not (x["recognized"] and y["recognized"]):
            dropped[pid] = "한 모델 이상이 모름"
            continue
        if gender != "any" and not (x["gender"] == gender and y["gender"] == gender):
            dropped[pid] = "성별 범위 밖 또는 불일치"
            continue
        tags: dict[str, Any] = {}
        conf: dict[str, float] = {}
        for f in singles:
            va, vb = x["tags"][f], y["tags"][f]
            if va != UNKNOWN and vb != UNKNOWN:
                compared[f] += 1
            if va == vb and va != UNKNOWN:
                agree[f] += 1
                tags[f] = va
                conf[f] = min(x["confidence"][f], y["confidence"][f])
            else:
                tags[f] = UNKNOWN
        for f in multis:
            sa, sb = x["tags"][f], y["tags"][f]
            if sa and sb:
                compared[f] += 1
            inter = [v for v in sa if v in sb]
            if inter:
                agree[f] += 1
            tags[f] = inter
            conf[f] = min(x["confidence"][f], y["confidence"][f])
        merged[pid] = {"tags": tags, "confidence": conf}
    stats = {
        "kept": len(merged),
        "dropped": dropped,
        "agreement": {
            f: {
                "agreed": agree[f],
                "compared": compared[f],
                "rate": round(agree[f] / compared[f], 3) if compared[f] else None,
            }
            for f in agree
        },
    }
    return merged, stats
