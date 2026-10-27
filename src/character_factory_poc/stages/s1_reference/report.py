"""S1 보고서: 후보 정렬·근거·한계·재현성 (LLD §8.1 report, FR-07, FR-08)."""

from __future__ import annotations

from statistics import median, quantiles

from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.schema import validate
from character_factory_poc.contracts.reference import (
    AppearanceFeatures,
    Person,
    RankingPeople,
    RankingScope,
    ReferenceReport,
    ReportSettings,
    Reproducibility,
)
from character_factory_poc.stages.s1_reference.cluster import (
    adjusted_rand_index,
    agglomerate,
    common_tags,
    vectorize,
)

CAUTIONS = [
    "화제성 순위(언급량 기반)를 외모 인기의 대리 지표로 썼다. 순위가 외모 때문인지 활동·작품 때문인지 분리하지 못했다.",
    "외모 특징은 텍스트 모델의 기억에서 왔고 사진으로 확인하지 않았다. 개별 인물의 특징은 틀릴 수 있어 여러 명의 공통 특징만 썼다.",
    "팬덤·소속사·작품 노출 효과를 분리하지 못했다.",
]


def normalization_text(min_list_size: int) -> str:
    return (
        "순위를 같은 목록 안의 백분위 (목록 크기 - 순위 + 1) / 목록 크기로 바꿨다(1위 = 1.0). "
        f"목록 크기가 {min_list_size}보다 작으면 정규화하지 않았다. "
        "여러 목록에 있는 인물은 가장 높은 백분위를 썼다. 다른 목록의 원점수는 직접 비교하지 않았다."
    )


def person_percentile(p: Person) -> float | None:
    vals = [a.percentile for a in p.appearances if a.percentile is not None]
    return max(vals) if vals else None


def _popularity(members: list[str], people: dict[str, Person]) -> dict:
    vals = [x for m in members if (x := person_percentile(people[m])) is not None]
    if not vals:
        med = iqr = None
    elif len(vals) == 1:
        med, iqr = vals[0], 0.0
    else:
        q = quantiles(vals, n=4, method="inclusive")
        med, iqr = round(median(vals), 4), round(q[2] - q[0], 4)
    return {
        "medianPercentile": med,
        "iqr": iqr,
        "normalizedCount": len(vals),
        "unnormalizedCount": len(members) - len(vals),
    }


def _labels(report: ReferenceReport) -> dict[str, str]:
    out = {m: c.clusterId for c in report.candidates for m in c.members}
    for i, d in enumerate(report.dropped):
        out.update({m: f"d{i}" for m in d.members})
    return out


def build_report(
    *,
    subject_id: str,
    rev: str,
    ranking_sha: str,
    features_sha: str,
    vocab_version: str,
    scope: RankingScope,
    settings: ReportSettings,
    people: RankingPeople,
    features: AppearanceFeatures,
    previous: tuple[str, ReferenceReport | None] | None = None,
) -> ReferenceReport:
    by_id = {p.personId: p for p in people.people}
    excluded = []
    vectors = {}
    feats = {}
    for f in features.features:
        if not f.recognized:
            excluded.append(
                {
                    "personId": f.personId,
                    "reason": "모델이 이 인물의 외모를 모른다고 답했다(recognized=false).",
                }
            )
            continue
        v = vectorize(f)
        if not v:
            excluded.append({"personId": f.personId, "reason": "알려진 외모 특징이 없다."})
            continue
        vectors[f.personId] = v
        feats[f.personId] = f

    candidates, dropped = [], []
    for members in agglomerate(vectors, settings.clusterK) if vectors else []:
        common, shares = common_tags(members, feats)
        n = len(members)
        if n < settings.minMembers:
            dropped.append(
                {
                    "members": members,
                    "reason": f"구성원 {n}명으로 기준 {settings.minMembers}명 미만이다. "
                    "한 사람의 묘사가 될 수 있어 후보에서 뺐다(D-0017).",
                }
            )
            continue
        if len(common) < settings.minCommonFields:
            dropped.append(
                {
                    "members": members,
                    "reason": f"과반이 공유하는 특징 필드가 {len(common)}개로 기준 "
                    f"{settings.minCommonFields}개 미만이다.",
                }
            )
            continue
        lists = {a.listId for m in members for a in by_id[m].appearances}
        pop = _popularity(members, by_id)
        limitations = []
        if len(lists) == 1:
            limitations.append(
                "목록 하나에서만 나온 외모군이다. 다른 분류·기간 목록에서도 반복되는지 확인되지 않았다."
            )
        if pop["unnormalizedCount"]:
            limitations.append(
                f"구성원 {pop['unnormalizedCount']}명은 목록이 짧아 순위 백분위를 계산하지 못했다."
            )
        candidates.append(
            {
                "members": members,
                "memberCount": n,
                "commonTags": common,
                "tagShares": shares,
                "listCount": len(lists),
                "popularity": pop,
                "limitations": limitations,
            }
        )

    if not candidates:
        reasons = [d["reason"] for d in dropped] or ["특징을 알 수 있는 인물이 없다."]
        raise CheckFailed(
            "s1",
            [
                f"구성원 {settings.minMembers}명 이상이 특징을 공유하는 외모군이 없다. "
                "목록을 늘리거나 cluster_k를 줄여 다시 돈다.",
                *reasons,
            ],
        )

    def sort_key(c: dict):
        med = c["popularity"]["medianPercentile"]
        return (
            -c["listCount"],
            -(med if med is not None else -1.0),
            -c["memberCount"],
            c["members"][0],
        )

    candidates.sort(key=sort_key)
    ordering = []
    for i, c in enumerate(candidates, start=1):
        c["clusterId"] = f"c{i}"
        c["schemaVersion"] = "appearance-cluster-v1"
        pop = c["popularity"]
        if pop["medianPercentile"] is None:
            pop_text = "순위 백분위는 정규화할 수 없었다"
        else:
            pop_text = f"순위 백분위 중앙값 {pop['medianPercentile']:.2f}(IQR {pop['iqr']:.2f})"
        ordering.append(
            {
                "clusterId": c["clusterId"],
                "rationale": f"목록 {c['listCount']}개에 걸쳐 {c['memberCount']}명이 공유하는 특징이다. {pop_text}.",
            }
        )
    dropped.sort(key=lambda d: d["members"][0])

    repro = {"previousRev": None, "agreementWithPrevious": None, "comparedPeople": 0}
    report = validate(
        "reference-report-v2",
        {
            "subjectId": subject_id,
            "referenceRev": rev,
            "rankingSha256": ranking_sha,
            "featuresSha256": features_sha,
            "vocabVersion": vocab_version,
            "scope": scope.model_dump(),
            "settings": settings.model_dump(),
            "normalization": normalization_text(settings.minListSizeForPercentile),
            "candidates": candidates,
            "ordering": ordering,
            "dropped": dropped,
            "excludedPeople": excluded,
            "cautions": CAUTIONS,
            "reproducibility": repro,
        },
    )
    if previous is not None:
        prev_rev, prev = previous
        repro["previousRev"] = prev_rev
        # 이전 보고서가 옛 계약(v1)이면 prev는 None이고 일치도 비교를 건너뛴다(D-0021).
        if prev is not None and prev.rankingSha256 == ranking_sha:
            ari, n = adjusted_rand_index(_labels(prev), _labels(report))  # type: ignore[arg-type]
            repro["agreementWithPrevious"] = ari
            repro["comparedPeople"] = n
        report = report.model_copy(
            update={"reproducibility": Reproducibility.model_validate(repro)}
        )
    return report  # type: ignore[return-value]
