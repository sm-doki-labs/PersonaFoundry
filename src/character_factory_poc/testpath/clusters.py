"""교차 확인한 cluster 칸으로 외모군을 나누고, 외모군마다 detail 칸 다수결을 정한다."""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any

from character_factory_poc.stages.s1_reference.cluster import Vector, agglomerate
from character_factory_poc.testpath.vocab2 import (
    UNKNOWN,
    cluster_multi,
    cluster_single,
    detail_single,
    phrase,
)


def basis_fields(vocab: dict[str, Any], agreement: dict[str, dict[str, Any]]) -> list[str]:
    """외모군을 나눌 단일 칸: 두 모델 일치율이 기준 이상이고 제외 목록에 없는 칸."""
    basis = vocab.get("clusterBasis", {})
    floor = float(basis.get("minAgreement", 0.6))
    excluded = set(basis.get("exclude", []))
    fields = []
    for f in [*cluster_single(vocab), *detail_single(vocab)]:
        rate = (agreement.get(f) or {}).get("rate")
        if f not in excluded and rate is not None and rate >= floor:
            fields.append(f)
    return fields


def vectorize(entry: dict[str, Any], vocab: dict[str, Any], fields: list[str]) -> Vector:
    weight = float(vocab.get("clusterBasis", {}).get("vibeWeight", 1.0))
    v: Vector = {}
    for f in fields:
        val = entry["tags"][f]
        if val != UNKNOWN:
            v[f"{f}={val}"] = 1.0
    for f in cluster_multi(vocab):
        for val in entry["tags"][f]:
            v[f"{f}={val}"] = weight
    return v


def usable(entry: dict[str, Any], fields: list[str], min_fields: int = 4) -> bool:
    known = sum(1 for f in fields if entry["tags"][f] != UNKNOWN)
    return bool(entry["tags"].get("vibe")) and known >= min_fields


def best_partition(
    vectors: dict[str, Vector], *, min_members: int = 3, max_k: int = 7
) -> tuple[int, list[list[str]]]:
    """여러 k로 나눠 보고, 구성원 min_members 이상인 외모군 수가 가장 많은 k를 고른다.

    동점이면 그 외모군들에 들어간 인원이 많은 쪽, 그다음 k가 큰 쪽이다.
    """
    n = len(vectors)
    best: tuple[tuple[int, int, int], int, list[list[str]]] | None = None
    for k in range(2, min(max_k, max(2, n // min_members)) + 1):
        groups = agglomerate(vectors, k)
        viable = [g for g in groups if len(g) >= min_members]
        key = (len(viable), sum(len(g) for g in viable), k)
        if best is None or key > best[0]:
            best = (key, k, groups)
    if best is None:
        return 1, [sorted(vectors)]
    return best[1], best[2]


def _majority(values: list[str], n: int) -> tuple[str | None, dict[str, float]]:
    counts = Counter(v for v in values if v != UNKNOWN)
    shares = {v: round(c / n, 3) for v, c in sorted(counts.items())}
    if not counts:
        return None, shares
    val, c = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return (val if c * 2 > n else None), shares


def profile(
    cid: str,
    members: list[str],
    merged: dict[str, dict[str, Any]],
    popularity: dict[str, float],
    vocab: dict[str, Any],
) -> dict[str, Any]:
    """외모군 요약. members(personId)는 내부 기록이고 프롬프트에는 태그만 쓴다."""
    n = len(members)
    common: dict[str, Any] = {}
    shares: dict[str, Any] = {}
    for f in cluster_single(vocab):
        val, sh = _majority([merged[m]["tags"][f] for m in members], n)
        shares[f] = sh
        if val:
            common[f] = val
    vibe_counts = Counter(v for m in members for v in merged[m]["tags"]["vibe"])
    shares["vibe"] = {v: round(c / n, 3) for v, c in sorted(vibe_counts.items())}
    vibe = [v for v, c in sorted(vibe_counts.items(), key=lambda kv: (-kv[1], kv[0])) if c * 2 > n]
    if not vibe and vibe_counts:
        vibe = [sorted(vibe_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]]
    common["vibe"] = vibe[:2]
    details: dict[str, Any] = {}
    open_fields: dict[str, list[str]] = {}
    for f in detail_single(vocab):
        vals = [merged[m]["tags"][f] for m in members]
        known = [v for v in vals if v != UNKNOWN]
        counts = Counter(known)
        shares[f] = {v: round(c / n, 3) for v, c in sorted(counts.items())}
        if not counts:
            continue
        ordered = [v for v, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
        top, top_c = ordered[0], counts[ordered[0]]
        if top_c >= 2 and top_c * 2 >= len(known):
            details[f] = top
        else:
            open_fields[f] = ordered
    pops = [popularity[m] for m in members if popularity.get(m) is not None]
    label_parts = [phrase(vocab, "vibe", v, "ko") for v in common["vibe"]]
    for f in ("faceShape", "featureIntensity"):
        if f in common:
            label_parts.append(phrase(vocab, f, common[f], "ko"))
    for f in ("jawline", "eyeTail"):
        if f in details:
            label_parts.append(phrase(vocab, f, details[f], "ko"))
    return {
        "clusterId": cid,
        "label": " · ".join(label_parts) or cid,
        "memberCount": n,
        "members": members,
        "common": common,
        "details": details,
        "openFields": open_fields,
        "shares": shares,
        "popularity": round(median(pops), 4) if pops else None,
    }


def allocate(
    total: int, clusters: list[dict[str, Any]], max_clusters: int = 5
) -> list[tuple[dict[str, Any], int]]:
    """인기순 상위 외모군에 후보 수를 고르게 나눈다(앞쪽부터 1장씩 더 받는다)."""
    chosen = sorted(clusters, key=lambda c: (-(c["popularity"] or 0), c["clusterId"]))[
        :max_clusters
    ]
    if not chosen:
        return []
    base, extra = divmod(total, len(chosen))
    return [(c, base + (1 if i < extra else 0)) for i, c in enumerate(chosen)]
