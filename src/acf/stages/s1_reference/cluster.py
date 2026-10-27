"""S1 외모군 군집 (LLD §8.1 cluster). 외부 의존 없는 결정적 평균 연결 계층 군집(D-0018)."""

from __future__ import annotations

from collections import Counter
from math import comb, sqrt

from acf.contracts.reference import MULTI_FIELDS, SINGLE_FIELDS, PersonFeatures

UNKNOWN = "unknown"
Vector = dict[str, float]


def vectorize(f: PersonFeatures) -> Vector:
    """필드·값마다 한 차원. 값에는 그 필드의 확신도(없으면 1.0)를 넣는다."""
    v: Vector = {}
    for field in SINGLE_FIELDS:
        val = getattr(f.tags, field)
        if val != UNKNOWN:
            v[f"{field}={val}"] = float(f.confidence.get(field, 1.0))
    for field in MULTI_FIELDS:
        for val in getattr(f.tags, field):
            v[f"{field}={val}"] = float(f.confidence.get(field, 1.0))
    return v


def cosine_distance(a: Vector, b: Vector) -> float:
    na = sqrt(sum(x * x for x in a.values()))
    nb = sqrt(sum(x * x for x in b.values()))
    if na == 0 or nb == 0:
        return 1.0
    dot = sum(x * b.get(k, 0.0) for k, x in a.items())
    return max(0.0, 1.0 - dot / (na * nb))


def agglomerate(vectors: dict[str, Vector], k: int) -> list[list[str]]:
    """평균 연결 거리가 가장 작은 쌍을 k개가 될 때까지 합친다. 동점은 구성원 튜플 순서로 정한다."""
    ids = sorted(vectors)
    dist: dict[tuple[str, str], float] = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            dist[(a, b)] = cosine_distance(vectors[a], vectors[b])

    def d(a: str, b: str) -> float:
        return dist[(a, b) if a < b else (b, a)]

    clusters: list[tuple[str, ...]] = [(i,) for i in ids]
    while len(clusters) > max(k, 1):
        best: tuple[tuple[float, tuple[str, ...], tuple[str, ...]], int, int] | None = None
        for x in range(len(clusters)):
            for y in range(x + 1, len(clusters)):
                A, B = clusters[x], clusters[y]
                avg = sum(d(a, b) for a in A for b in B) / (len(A) * len(B))
                key = (round(avg, 9), A, B)
                if best is None or key < best[0]:
                    best = (key, x, y)
        assert best is not None
        _, x, y = best
        merged = tuple(sorted(clusters[x] + clusters[y]))
        clusters = [c for i, c in enumerate(clusters) if i not in (x, y)] + [merged]
        clusters.sort()
    return [list(c) for c in clusters]


def common_tags(
    members: list[str], feats: dict[str, PersonFeatures]
) -> tuple[dict[str, str | list[str]], dict[str, dict[str, float]]]:
    """구성원 과반이 가진 태그를 공통 특징으로 본다. 비율표도 함께 돌려준다."""
    n = len(members)
    common: dict[str, str | list[str]] = {}
    shares: dict[str, dict[str, float]] = {}
    for field in SINGLE_FIELDS:
        counts = Counter(getattr(feats[m].tags, field) for m in members)
        counts.pop(UNKNOWN, None)
        if not counts:
            continue
        shares[field] = {v: round(c / n, 4) for v, c in sorted(counts.items())}
        val, c = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        if c * 2 > n:
            common[field] = val
    for field in MULTI_FIELDS:
        counts = Counter(v for m in members for v in getattr(feats[m].tags, field))
        if not counts:
            continue
        shares[field] = {v: round(c / n, 4) for v, c in sorted(counts.items())}
        vals = [v for v, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c * 2 > n]
        if vals:
            common[field] = vals
    return common, shares


def adjusted_rand_index(a: dict[str, str], b: dict[str, str]) -> tuple[float | None, int]:
    """두 군집 배정의 ARI와 비교한 인물 수. 겹치는 인물이 2명 미만이면 None."""
    ids = sorted(set(a) & set(b))
    n = len(ids)
    if n < 2:
        return None, n
    cont = Counter((a[i], b[i]) for i in ids)
    sum_ij = sum(comb(c, 2) for c in cont.values())
    sa = sum(comb(c, 2) for c in Counter(a[i] for i in ids).values())
    sb = sum(comb(c, 2) for c in Counter(b[i] for i in ids).values())
    expected = sa * sb / comb(n, 2)
    max_index = (sa + sb) / 2
    if max_index == expected:
        return 1.0, n
    return round((sum_ij - expected) / (max_index - expected), 4), n
